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


class GemmaAnalyzer:
    """Handles advanced conversation analysis using Gemma AI"""
    
    def __init__(self, rag_url: str, data_dir: str = "/app/instance/gemma_responses"):
        self.rag_url = rag_url
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Default comprehensive analysis prompt
        self.default_prompt_template = """Analyze the following conversation transcripts for communication patterns.

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

    async def fetch_transcripts(
        self,
        speakers: Optional[List[str]] = None,
        emotions: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 20,
        headers: Optional[Dict[str, str]] = None
    ) -> List[Dict[str, Any]]:
        """Fetch transcripts from RAG service with filters"""
        params = {"limit": limit}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.rag_url}/transcripts/recent",
                params=params,
                headers=headers or {}
            )
            response.raise_for_status()
            data = response.json()
            
            # Extract transcripts from response
            transcripts = data.get("transcripts") or data.get("items") or []
            
            # Apply filters
            filtered = []
            for t in transcripts:
                # Speaker filter
                if speakers:
                    speaker = t.get("speaker") or t.get("primary_speaker") or ""
                    if not any(s.lower() in speaker.lower() for s in speakers):
                        continue
                
                # Emotion filter
                if emotions:
                    emotion = t.get("emotion") or t.get("dominant_emotion") or ""
                    if emotion.lower() not in [e.lower() for e in emotions]:
                        continue
                
                filtered.append(t)
            
            return filtered[:limit]
    
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
        
        # Fetch transcripts
        transcripts = await self.fetch_transcripts(
            speakers=filters.get("speakers"),
            emotions=filters.get("emotions"),
            start_date=filters.get("start_date"),
            end_date=filters.get("end_date"),
            limit=filters.get("limit", 20),
            headers=service_headers
        )
        
        if not transcripts:
            return {
                "success": False,
                "error": "No transcripts found matching the filters"
            }
        
        # Format transcripts
        formatted_transcripts = self.format_transcripts_for_analysis(transcripts)

        # Prepare prompt template
        prompt_template = custom_prompt or self.default_prompt_template

        # Safety: ensure prompt + response tokens won't exceed model context window
        # Estimate tokens by chars/4 (approx). Use conservative default context of 2048.
        model_context_window = 2048
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
        else:
            final_prompt = tentative_prompt

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
