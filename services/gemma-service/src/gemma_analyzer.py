"""
Gemma Advanced Analysis Module
Analyzes conversation transcripts for patterns, fallacies, emotional triggers
Saves all responses to /app/instance/gemma_responses/ for record-keeping
"""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
import inspect
import httpx
import logging


class GemmaAnalyzer:
    """Handles advanced conversation analysis using Gemma AI"""
    
    def __init__(
        self,
        rag_url: str,
        data_dir: str = "/app/instance/gemma_responses",
        default_prompt_template: Optional[str] = None,
    ):
        self.rag_url = rag_url
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._logger = logging.getLogger(__name__)
        self.default_prompt_template = self._load_default_prompt(default_prompt_template)
        # Detect model context window from environment for smarter prompt trimming
        try:
            self.model_context_window = int(os.getenv("GEMMA_CONTEXT_SIZE", "2048") or 2048)
        except Exception:
            self.model_context_window = 2048

    def _load_default_prompt(self, override: Optional[str]) -> str:
        """
        Determine the default prompt template in this precedence order:
          1. Explicit override passed to the constructor
          2. Text from GEMMA_ANALYZER_DEFAULT_PROMPT_PATH file (if exists)
          3. Text from GEMMA_ANALYZER_DEFAULT_PROMPT env variable
          4. Built-in comprehensive template (legacy default)
        The template must include {transcripts}; if missing, append one.
        """
        built_in = """Analyze the following conversation transcripts for communication patterns.

Focus on identifying:
1. **Logical Fallacies**: Name any fallacies used (ad hominem, straw man, false dilemma, etc.)
2. **Snippiness**: Identify curt, dismissive, or unnecessarily brief responses
3. **Hyperbolic Language**: Point out exaggerated, extreme, or dramatic phrasing
4. **Emotional Triggers**: Note what causes emotional reactions and why

For each issue found, provide:
- Specific quote from the transcript
- Why it's problematic
- A better alternative approach

Then provide a 2-3 sentence summary of the overall communication style and root emotional causes.

Transcripts:
{transcripts}

Provide your analysis in clear, structured sections."""
        logger = logging.getLogger(__name__)
        source = "override"
        if override:
            template = override
        else:
            prompt_path = os.getenv("GEMMA_ANALYZER_DEFAULT_PROMPT_PATH")
            if prompt_path:
                candidate = Path(prompt_path)
                if candidate.is_file():
                    template = candidate.read_text(encoding="utf-8")
                    source = f"path:{prompt_path}"
                else:
                    template = os.getenv("GEMMA_ANALYZER_DEFAULT_PROMPT")
                    source = "env:GEMMA_ANALYZER_DEFAULT_PROMPT"
            else:
                template = os.getenv("GEMMA_ANALYZER_DEFAULT_PROMPT")
                source = "env:GEMMA_ANALYZER_DEFAULT_PROMPT"
            if not template:
                template = built_in
                source = "built-in"
        if "{transcripts}" not in template:
            template = template.rstrip() + "\n\nTranscripts:\n{transcripts}\n"
            logger.debug("Appended '{transcripts}' placeholder to default prompt template")
        logger.info("GemmaAnalyzer default prompt source: %s", source)
        return template

    async def fetch_transcripts(
        self,
        speakers: Optional[List[str]] = None,
        emotions: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 20,
        headers: Optional[Dict[str, str]] = None,
        keywords: Optional[str] = None,
        match: str = "any",
        search_type: str = "keyword",
        context_lines: int = 3,
    ) -> List[Dict[str, Any]]:
        """Fetch transcript segments from RAG service using /transcripts/query with graceful fallback."""
        payload: Dict[str, Any] = {
            "limit": limit,
            "offset": 0,
            "sort_by": "created_at",
            "order": "desc",
            "context_lines": max(0, min(int(context_lines or 0), 10)),
        }
        if speakers:
            payload["speakers"] = speakers
        if emotions:
            payload["emotions"] = emotions
        if start_date:
            payload["start_date"] = start_date
        if end_date:
            payload["end_date"] = end_date
        if keywords:
            payload["keywords"] = keywords
            payload["match"] = (match or "any").lower()
            payload["search_type"] = (search_type or "keyword").lower()

        # Prefer rich query endpoint for precise selection
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self.rag_url}/transcripts/query",
                    json=payload,
                    headers=headers or {},
                )
                if resp.status_code == 404:
                    raise httpx.HTTPStatusError("/transcripts/query not found", request=resp.request, response=resp)
                resp.raise_for_status()
                data = resp.json() or {}
                items = data.get("items") or []
                self._logger.info("RAG /transcripts/query -> %s items (limit=%s)", len(items), limit)
                if items:
                    return items[:limit]
        except httpx.HTTPStatusError as exc:
            self._logger.warning("/transcripts/query failed (%s): %s; falling back to /transcripts/recent",
                                 getattr(exc.response, 'status_code', 'n/a'), str(exc))
        except Exception as exc:
            self._logger.warning("/transcripts/query error: %s; falling back to /transcripts/recent", exc)

        # Fallback: use recent transcripts and client-side filtering
        recent_params = {"limit": max(limit * 5, 50)}
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.get(
                    f"{self.rag_url}/transcripts/recent",
                    params=recent_params,
                    headers=headers or {},
                )
                r.raise_for_status()
                data = r.json() or {}
                transcripts = data.get("transcripts") or []
        except Exception as exc:
            self._logger.error("Fallback /transcripts/recent failed: %s", exc)
            return []

        segs_out: List[Dict[str, Any]] = []
        speakers_set = {s.lower() for s in (speakers or [])}
        emotions_set = {e.lower() for e in (emotions or [])}
        kw_list = [k.strip().lower() for k in (keywords or "").split(",") if k.strip()]
        require_all = (match or "any").lower() == "all"
        ctx = max(0, min(int(context_lines or 0), 10))
        for tr in transcripts:
            created = tr.get("created_at") or tr.get("timestamp")
            segs = tr.get("segments") or []
            for idx, seg in enumerate(segs):
                sp = (seg.get("speaker") or "").lower()
                if speakers_set and sp not in speakers_set:
                    continue
                emo = (seg.get("emotion") or tr.get("dominant_emotion") or "").lower()
                if emotions_set and emo not in emotions_set:
                    continue
                text_val = (seg.get("text") or "").strip()
                if kw_list:
                    hits = [kw for kw in kw_list if kw in text_val.lower()]
                    if require_all and len(hits) != len(kw_list):
                        continue
                    if not require_all and not hits:
                        continue
                context_before: List[Dict[str, Any]] = []
                if ctx:
                    start_idx = max(0, idx - ctx)
                    for j in range(start_idx, idx):
                        prev = segs[j]
                        context_before.append({
                            "speaker": prev.get("speaker"),
                            "text": prev.get("text"),
                            "emotion": prev.get("emotion") or tr.get("dominant_emotion"),
                        })
                segs_out.append({
                    "segment_id": seg.get("id") or f"fallback-{tr.get('job_id','job')}-{idx}",
                    "transcript_id": tr.get("id"),
                    "job_id": tr.get("job_id"),
                    "speaker": seg.get("speaker"),
                    "emotion": seg.get("emotion") or tr.get("dominant_emotion"),
                    "text": text_val,
                    "created_at": created,
                    "start_time": seg.get("start_time"),
                    "end_time": seg.get("end_time"),
                    "context_before": context_before,
                })
                if len(segs_out) >= limit:
                    return segs_out
        return segs_out[:limit]
    
    def format_transcripts_for_analysis(self, transcripts: List[Dict[str, Any]]) -> str:
        """Format transcripts into readable text for Gemma"""
        formatted_lines = []
        
        for i, t in enumerate(transcripts, 1):
            speaker = t.get("speaker") or t.get("primary_speaker") or "Unknown"
            text = t.get("text") or t.get("full_text") or t.get("snippet") or ""
            emotion = t.get("emotion") or t.get("dominant_emotion") or "neutral"
            timestamp = t.get("created_at") or t.get("timestamp") or ""
            
            formatted_lines.append(f"--- Transcript {i} ---")
            formatted_lines.append(f"Speaker: {speaker}")
            formatted_lines.append(f"Emotion: {emotion}")
            if timestamp:
                formatted_lines.append(f"Time: {timestamp}")
            # Include context_before if provided (segment-level records)
            context_before = t.get("context_before") or []
            if isinstance(context_before, list) and context_before:
                formatted_lines.append("Context before:")
                for ctx in context_before:
                    cs = ctx.get("speaker") or "Speaker"
                    ct = ctx.get("text") or ""
                    ce = ctx.get("emotion") or ""
                    formatted_lines.append(f"  - {cs}{' (' + ce + ')' if ce else ''}: {ct}")
            formatted_lines.append(f"Text: {text}")
            
            # Add segments if available
            segments = t.get("segments") or []
            if segments and isinstance(segments, list):
                formatted_lines.append("Segments:")
                for j, seg in enumerate(segments[:10], 1):  # Limit to 10 segments
                    if isinstance(seg, dict):
                        seg_speaker = seg.get("speaker") or speaker
                        seg_text = seg.get("text") or ""
                        seg_emotion = seg.get("emotion") or "neutral"
                        if seg_text:
                            formatted_lines.append(f"  {j}. [{seg_speaker}] ({seg_emotion}): {seg_text}")
            
            formatted_lines.append("")  # Blank line between transcripts
        
        return "\n".join(formatted_lines)
    
    def save_response(
        self,
        analysis_type: str,
        filters: Dict[str, Any],
        custom_prompt: str,
        transcripts_count: int,
        gemma_response: str,
        model: str,
        processing_time: float
    ) -> str:
        """Save Gemma response to file and return filepath"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Create filename from filters
        filter_parts = []
        if filters.get("speakers"):
            filter_parts.append(f"speakers_{'-'.join(filters['speakers'][:2])}")
        if filters.get("emotions"):
            filter_parts.append(f"emotions_{'-'.join(filters['emotions'][:2])}")
        if filters.get("start_date"):
            filter_parts.append(f"from_{filters['start_date']}")
        
        filter_summary = "_".join(filter_parts) if filter_parts else "all"
        filename = f"{timestamp}_{analysis_type}_{filter_summary}.json"
        filepath = self.data_dir / filename
        
        # Prepare data
        data = {
            "timestamp": datetime.now().isoformat(),
            "analysis_type": analysis_type,
            "filters": filters,
            "custom_prompt": custom_prompt,
            "transcripts_analyzed": transcripts_count,
            "gemma_response": gemma_response,
            "model": model,
            "processing_time_seconds": round(processing_time, 2)
        }
        
        # Save to file
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        return str(filepath)
    
    async def run_analysis(
        self,
        llm_callable,
        filters: Dict[str, Any],
        custom_prompt: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.3,
        service_headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Run comprehensive analysis with custom prompt
        
        Args:
            llm_callable: The Gemma LLM function to call
            filters: Dict with speakers, emotions, start_date, end_date, limit
            custom_prompt: Custom prompt template (uses default if None)
            max_tokens: Max tokens for Gemma response
            temperature: Temperature for Gemma generation
            service_headers: Service auth headers for RAG requests
        
        Returns:
            Dict with analysis results and saved file path
        """
        start_time = datetime.now()
        
        self._logger.info("run_analysis filters=%s custom_prompt=%s limit=%s", filters, bool(custom_prompt), filters.get("limit", 20))
        # Fetch transcripts
        transcripts = await self.fetch_transcripts(
            speakers=filters.get("speakers"),
            emotions=filters.get("emotions"),
            start_date=filters.get("start_date"),
            end_date=filters.get("end_date"),
            limit=filters.get("limit", 20),
            headers=service_headers,
            keywords=filters.get("keywords"),
            match=filters.get("match", "any"),
            search_type=filters.get("search_type", "keyword"),
            context_lines=filters.get("context_lines", 3),
        )
        
        if not transcripts:
            self._logger.warning("No transcripts found for filters=%s", filters)
            return {
                "success": False,
                "error": "No transcripts found matching the filters"
            }
        
        # Format transcripts
        formatted_transcripts = self.format_transcripts_for_analysis(transcripts)

        # Prepare prompt template
        prompt_template = custom_prompt or self.default_prompt_template

        # Safety: ensure prompt + response tokens won't exceed model context window
        # Estimate tokens by chars/4 (approx). Default to configured context window
        model_context_window = self.model_context_window
        try:
            # allow callers to override by placing 'model_context' in filters
            if filters.get("model_context"):
                model_context_window = int(filters.get("model_context"))
        except Exception:
            pass

        # Build tentative prompt and trim transcripts if necessary
        tentative_prompt = prompt_template.replace("{transcripts}", formatted_transcripts)
        estimated_tokens = max(1, int(len(tentative_prompt) / 4))
        # If estimated tokens + desired output exceed context, trim transcripts
        if estimated_tokens + max_tokens > model_context_window:
            allowed_prompt_tokens = max(256, model_context_window - max_tokens - 50)
            allowed_chars = int(allowed_prompt_tokens * 4)
            # Keep the last portion of the transcripts (most recent context)
            trimmed_transcripts = formatted_transcripts[-allowed_chars:]
            # Add a small header to indicate truncation
            trimmed_transcripts = (
                "[TRUNCATED: only the most recent transcripts included]\n" + trimmed_transcripts
            )
            final_prompt = prompt_template.replace("{transcripts}", trimmed_transcripts)
            self._logger.info(
                "Prompt trimmed from %s tokens to %s (context window %s)",
                estimated_tokens,
                allowed_prompt_tokens,
                model_context_window,
            )
        else:
            final_prompt = tentative_prompt
            self._logger.debug("Prompt size %s tokens within context window %s", estimated_tokens, model_context_window)

        # Call Gemma
        response = llm_callable(
            prompt=final_prompt,
            max_tokens=max_tokens,
            temperature=temperature
        )
        if inspect.isawaitable(response):
            response = await response
        
        # Extract response text
        gemma_text = ""
        model_name = "gemma-3-4b-it"
        
        if isinstance(response, dict):
            gemma_text = response.get("text") or response.get("response") or response.get("choices", [{}])[0].get("text", "")
            model_name = response.get("model") or model_name
        else:
            gemma_text = str(response)
        
        # Calculate processing time
        processing_time = (datetime.now() - start_time).total_seconds()
        self._logger.info(
            "Gemma run complete model=%s tokens=%s processing_time=%.2fs",
            model_name,
            response.get("usage", {}).get("completion_tokens", 0),
            processing_time,
        )

        # Save response to file
        saved_file = self.save_response(
            analysis_type="custom" if custom_prompt else "comprehensive",
            filters=filters,
            custom_prompt=final_prompt,
            transcripts_count=len(transcripts),
            gemma_response=gemma_text,
            model=model_name,
            processing_time=processing_time
        )
        
        return {
            "success": True,
            "analysis": gemma_text,
            "transcripts_analyzed": len(transcripts),
            "processing_time_seconds": round(processing_time, 2),
            "model": model_name,
            "saved_to": saved_file,
            "filters_applied": filters,
            "prompt_used": final_prompt[:200] + "..." if len(final_prompt) > 200 else final_prompt
        }
