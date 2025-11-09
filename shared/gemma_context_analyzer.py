#!/usr/bin/env python3
"""
Gemma Context Analyzer
Uses Gemma AI to analyze conversation context for snippy responses and hyperbolic language
Optimized for VRAM constraints with smart chunking
"""

import json
import sqlite3
import datetime
import re
from typing import Dict, List, Any, Tuple, Optional
from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from advanced_memory_service import AdvancedMemoryService


class GemmaContextAnalyzer:
    def __init__(self, memory_service: 'AdvancedMemoryService'):
        self.memory_service = memory_service
        # Use the db_path from memory_service, which should be set by that point
        # If not available, construct it
        if hasattr(memory_service, 'db_path') and memory_service.db_path:
            self.db_path = memory_service.db_path
        else:
            # Fallback - construct from current working directory
            from pathlib import Path
            self.db_path = str(Path.cwd() / "instance" / "memories.db")
        self.max_context_lines = 8   # Fewer lines speeds up prompts
        self.max_chunk_size = 1000   # Conservative for VRAM
        self.max_conversations = 50  # Upper bound of conversations to analyze
        self.max_triggers_per_conversation = 1  # Cap triggers per conversation
        self.max_parallel_requests = 3  # Concurrency limit for LLM calls
        
    def load_all_conversations(self) -> List[Dict]:
        """Load all conversations from database with fallback.

        Primary: memories where source_job_id LIKE 'imported_%'.
        Fallback: job_transcripts full_text entries if primary is empty.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            conversations: List[Dict] = []

            # Primary source: imported memories
            try:
                cursor.execute(
                    f"SELECT id, title, body, created_at, tags, source_job_id "
                    f"FROM memories WHERE source_job_id LIKE 'imported_%' "
                    f"ORDER BY created_at DESC LIMIT {int(self.max_conversations)}"
                )
                rows = cursor.fetchall()
                for row in rows:
                    conversations.append({
                        'id': row[0],
                        'title': row[1],
                        'body': row[2],
                        'created_at': row[3],
                        'tags': row[4],
                        'source_job_id': row[5],
                    })
            except Exception:
                pass

            # Fallback: use job_transcripts if no imported conversations
            if not conversations:
                try:
                    cursor.execute(
                        f"SELECT job_id, full_text, raw_json, created_at "
                        f"FROM job_transcripts ORDER BY created_at DESC LIMIT {int(self.max_conversations)}"
                    )
                    trs = cursor.fetchall()
                    for t in trs:
                        conversations.append({
                            'id': t[0],
                            'title': f'Job {t[0]}',
                            'body': t[1] or '',
                            'created_at': t[3],
                            'tags': '[]',
                            'source_job_id': t[0],
                        })
                except Exception:
                    pass

            conn.close()
            return conversations

        except Exception as e:
            print(f"Error loading conversations: {e}")
            return []
    
    def extract_conversation_text(self, conversation_body: str) -> List[str]:
        """Extract conversation text as lines"""
        # Find the conversation text section
        if 'Conversation Text:' in conversation_body:
            text_section = conversation_body.split('Conversation Text:')[1]
            if 'Emotions:' in text_section:
                text_section = text_section.split('Emotions:')[0]
            
            # Split into lines and clean
            lines = [line.strip() for line in text_section.split('\n') if line.strip()]
            return lines
        
        # Fallback: split the entire body
        lines = [line.strip() for line in conversation_body.split('\n') if line.strip()]
        return lines
    
    def find_emotional_triggers(self, lines: List[str]) -> List[int]:
        """Find line indices that contain emotional triggers"""
        emotional_keywords = [
            'angry', 'frustrated', 'mad', 'upset', 'annoyed', 'irritated',
            'disappointed', 'hurt', 'sad', 'worried', 'anxious', 'stressed',
            'excited', 'happy', 'joyful', 'thrilled', 'elated', 'ecstatic'
        ]
        
        trigger_lines = []
        for i, line in enumerate(lines):
            line_lower = line.lower()
            if any(keyword in line_lower for keyword in emotional_keywords):
                trigger_lines.append(i)
        
        return trigger_lines
    
    def get_context_window(self, lines: List[str], trigger_line: int) -> str:
        """Get context window around emotional trigger"""
        start = max(0, trigger_line - self.max_context_lines)
        end = min(len(lines), trigger_line + self.max_context_lines + 1)
        
        context_lines = lines[start:end]
        context_text = '\n'.join(context_lines)
        
        # Mark the trigger line
        trigger_in_context = trigger_line - start
        if trigger_in_context < len(context_lines):
            context_lines[trigger_in_context] = f"*** EMOTIONAL TRIGGER: {context_lines[trigger_in_context]} ***"
            context_text = '\n'.join(context_lines)
        
        return context_text

    def prepare_analysis_prompts(self) -> List[Dict[str, Any]]:
        """Prepare UI-driven analysis prompts without querying the LLM.

        Returns a list of dictionaries with conversation_id, trigger_line, and
        a prompt string following the user's requested format.
        """
        prompts: List[Dict[str, Any]] = []
        conversations = self.load_all_conversations()
        if not conversations:
            return prompts

        for conv in conversations:
            lines = self.extract_conversation_text(conv.get('body') or '')
            trigger_lines = self.find_emotional_triggers(lines)
            if not trigger_lines:
                continue
            capped = trigger_lines[: max(1, int(self.max_triggers_per_conversation))]
            for tl in capped:
                context = self.get_context_window(lines, tl)
                user_prompt = (
                    "Im going to give you 20 lines of conversation which looks for the following: "
                    "logical fallacy, snippiness, hyperbolic language. If found respond\n"
                    "Fallacy: what fallacy was used here\n"
                    "Snippiness: what was snippy\n"
                    "hyperbolic language: what was hyperbolic.\n\n"
                    "Then give a 1 sentence summary of why what emotion was caused.\n\n"
                    f"Context:\n{context}\n"
                )
                prompts.append({
                    'conversation_id': conv.get('id'),
                    'trigger_line': tl,
                    'prompt': user_prompt,
                })
        return prompts
    
    def query_gemma_for_snippy_analysis(self, context_text: str, conversation_id: str) -> Dict[str, Any]:
        """Query Gemma to analyze if responses are snippy"""
        prompt = f"""
        Analyze this conversation context for snippy responses. Focus on Pruitt's communication style.

        Context (20 lines before and after emotional trigger):
        {context_text}

        Please analyze:
        1. Is Pruitt being snippy, dismissive, or curt in their responses?
        2. Are the responses appropriately measured or overly brief?
        3. What specific phrases or patterns indicate snippiness?
        4. Rate the snippiness level from 1-10 (1 = very measured, 10 = very snippy)

        Respond in JSON format:
        {{
            "is_snippy": true/false,
            "snippiness_score": 1-10,
            "evidence": ["specific examples"],
            "context": "brief explanation"
        }}
        """
        
        try:
            if not self.memory_service._llm:
                return {"error": "LLM not available in memory service"}

            response = self.memory_service._llm(
                prompt=prompt,
                max_tokens=256,
                temperature=0.1,
                stop=["}"],
            )
            gemma_response = response['choices'][0]['text'] + "}"

            try:
                json_match = re.search(r"\{[\s\S]*?\}", str(gemma_response))
                if json_match:
                    json_str = json_match.group(0)
                    return json.loads(json_str)
                return self.parse_text_response(gemma_response, "snippy")
            except Exception:
                return self.parse_text_response(gemma_response, "snippy")

        except Exception as e:
            return {"error": str(e)}
    
    def query_gemma_for_hyperbolic_analysis(self, context_text: str, conversation_id: str) -> Dict[str, Any]:
        """Query Gemma to analyze if language is hyperbolic"""
        prompt = f"""
        Analyze this conversation context for hyperbolic language. Focus on Pruitt's communication style.

        Context (20 lines before and after emotional trigger):
        {context_text}

        Please analyze:
        1. Is Pruitt using hyperbolic, exaggerated, or extreme language?
        2. Are there absolute statements, superlatives, or dramatic phrases?
        3. What specific words or phrases indicate hyperbole?
        4. Rate the hyperbole level from 1-10 (1 = very measured, 10 = very hyperbolic)

        Respond in JSON format:
        {{
            "is_hyperbolic": true/false,
            "hyperbole_score": 1-10,
            "evidence": ["specific examples"],
            "context": "brief explanation"
        }}
        """
        
        try:
            if not self.memory_service._llm:
                return {"error": "LLM not available in memory service"}

            response = self.memory_service._llm(
                prompt=prompt,
                max_tokens=256,
                temperature=0.1,
                stop=["}"],
            )
            gemma_response = response['choices'][0]['text'] + "}"

            try:
                json_match = re.search(r"\{[\s\S]*?\}", str(gemma_response))
                if json_match:
                    json_str = json_match.group(0)
                    return json.loads(json_str)
                return self.parse_text_response(gemma_response, "hyperbolic")
            except Exception:
                return self.parse_text_response(gemma_response, "hyperbolic")

        except Exception as e:
            return {"error": str(e)}

    def query_gemma_combined(self, context_text: str, conversation_id: str) -> Dict[str, Any]:
        """Single-prompt combined analysis per item.

        Detect snippiness, hyperbolic language, and logical fallacies.
        Only mark items if they are clear, obvious, and high probability.
        Also return a 2–3 sentence summary with root-cause.
        """
        prompt = f"""
        You are a precise communication analyst.
        I will give you ~20 lines of conversation (10 before and 10 after a target line).
        Detect ONLY when clear, obvious, and high probability:
        - logical fallacy (name it)
        - snippiness (what exactly was snippy)
        - hyperbolic language (what exactly was hyperbolic)
        Then give a single concise sentence explaining the likely emotion caused and the root cause.

        Output strictly JSON only (no extra words) with this schema:
        {{
          "is_snippy": true|false,
          "is_hyperbolic": true|false,
          "fallacies": ["name", ...],
          "snippiness": "brief quote/explanation or empty",
          "hyperbolic": "brief quote/explanation or empty",
          "summary_emotion_cause": "one sentence"
        }}

        Context:
        {context_text}

        JSON:
        """

        try:
            if not self.memory_service._llm:
                return {"error": "LLM not available in memory service"}
            
            with self.memory_service.llm_lock:
                response = self.memory_service._llm(
                    prompt=prompt,
                    max_tokens=512,
                    temperature=0.1,
                    stop=["}"],
                )
            gemma_response = response['choices'][0]['text'] + "}"

            try:
                json_match = re.search(r"\{[\s\S]*?\}", str(gemma_response))
                if json_match:
                    json_str = json_match.group(0)
                    parsed = json.loads(json_str)
                    # Normalize fields
                    parsed.setdefault("is_snippy", False)
                    parsed.setdefault("is_hyperbolic", False)
                    if "logical_fallacies" in parsed and "fallacies" not in parsed:
                        parsed["fallacies"] = parsed.pop("logical_fallacies")
                    parsed.setdefault("fallacies", [])
                    parsed.setdefault("snippiness", "")
                    parsed.setdefault("hyperbolic", "")
                    parsed.setdefault("summary_emotion_cause", "")
                    return parsed
            except Exception:
                pass

            # Fallback: best-effort text parse
            text = str(gemma_response)
            lower = text.lower()
            return {
                "is_snippy": any(w in lower for w in ["snippy", "curt", "dismissive", "rude", "short"]),
                "is_hyperbolic": any(w in lower for w in ["hyperbol", "exaggerat", "extreme", "dramatic"]),
                "fallacies": [k for k in ["ad hominem", "straw man", "false dilemma", "slippery slope", "circular"] if k in lower],
                "snippiness": "",
                "hyperbolic": "",
                "summary_emotion_cause": text.strip().split("\n")[0][:200]
            }
        except Exception as e:
            return {"error": str(e)}
    
    def parse_text_response(self, text: str, analysis_type: str) -> Dict[str, Any]:
        """Parse text response when JSON parsing fails"""
        text_lower = text.lower()
        
        if analysis_type == "snippy":
            # Look for snippiness indicators
            is_snippy = any(word in text_lower for word in ['snippy', 'dismissive', 'curt', 'brief', 'short'])
            score = 5  # Default moderate score
            
            # Try to extract score
            score_match = re.search(r'(\d+)/10', text)
            if score_match:
                score = int(score_match.group(1))
            
            return {
                "is_snippy": is_snippy,
                "snippiness_score": score,
                "evidence": ["Analysis completed"],
                "context": text[:200] + "..." if len(text) > 200 else text
            }
        
        elif analysis_type == "hyperbolic":
            # Look for hyperbole indicators
            is_hyperbolic = any(word in text_lower for word in ['hyperbolic', 'exaggerated', 'extreme', 'dramatic'])
            score = 5  # Default moderate score
            
            # Try to extract score
            score_match = re.search(r'(\d+)/10', text)
            if score_match:
                score = int(score_match.group(1))
            
            return {
                "is_hyperbolic": is_hyperbolic,
                "hyperbole_score": score,
                "evidence": ["Analysis completed"],
                "context": text[:200] + "..." if len(text) > 200 else text
            }
        
        return {"error": "Unable to parse response"}
    
    def analyze_conversation_chunk(self, conversations: List[Dict], logs: Optional[List[str]] = None, log_callback: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
        """Analyze a chunk of conversations using Gemma (parallelized, capped)."""
        if logs is None:
            logs = []
        results = {
            'combined_analyses': [],
            'conversations_processed': 0,
            'emotional_triggers_found': 0
        }
        
        def emit(msg: str) -> None:
            logs.append(msg)
            print(msg)
            if log_callback:
                try:
                    log_callback(msg)
                except Exception:
                    pass

        task_counter = 0
        for conv in conversations:
            conversation_lines = self.extract_conversation_text(conv.get('body', ''))
            trigger_lines = self.find_emotional_triggers(conversation_lines)

            results['conversations_processed'] += 1
            if not trigger_lines:
                continue

            capped_triggers = trigger_lines[:max(1, int(self.max_triggers_per_conversation))]
            results['emotional_triggers_found'] += len(capped_triggers)

            for tl in capped_triggers:
                context_text = self.get_context_window(conversation_lines, tl)
                if len(context_text) > 1200:
                    context_text = context_text[:1200]

                task_counter += 1
                emit(f"[Task {task_counter}] Starting Gemma analysis for conversation {conv.get('id')} at trigger line {tl}")
                try:
                    analysis = self.query_gemma_combined(context_text, conv.get('id'))
                    emit(f"[Task {task_counter}] Gemma analysis completed for conversation {conv.get('id')}")
                except Exception as e:
                    analysis = {"error": str(e)}
                    emit(f"[Task {task_counter}] Gemma error for conversation {conv.get('id')}: {e}")

                analysis['conversation_id'] = conv.get('id')
                analysis['trigger_line'] = tl
                analysis['timestamp'] = conv.get('created_at')
                results['combined_analyses'].append(analysis)

        return results
    
    def get_comprehensive_gemma_analysis(
        self, 
        log_callback: Optional[Callable[[str], None]] = None,
        emotion_filter: Optional[List[str]] = None,
        time_period: Optional[str] = None,
        min_confidence: float = 0.7,
        speakers: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Get comprehensive analysis using Gemma AI with optional filters"""
        logs: List[str] = []
        def log(msg: str) -> None:
            print(msg)
            logs.append(msg)
            if log_callback:
                try:
                    log_callback(msg)
                except Exception:
                    pass

        log("🧠 Gemma Context Analyzer - Starting Analysis")
        log("=" * 60)
        
        if emotion_filter:
            log(f"🎯 Filtering emotions: {', '.join(emotion_filter)}")
        if speakers:
            log(f"👤 Filtering speakers: {', '.join(speakers)}")
        if time_period:
            log(f"📅 Time period: {time_period}")
        
        conversations = self.load_all_conversations()
        
        if not conversations:
            return {
                'error': 'No conversations found',
                'snippy_meter': {'score': 0, 'level': 'low'},
                'hyperbolic_meter': {'score': 0, 'level': 'low'}
            , 'logs': logs}
        
        log(f"📊 Found {len(conversations)} conversations")
        
        # Process in chunks for VRAM optimization
        chunks = []
        for i in range(0, len(conversations), self.max_chunk_size):
            chunks.append(conversations[i:i + self.max_chunk_size])
        
        log(f"🔄 Processing in {len(chunks)} chunks for VRAM optimization")
        
        all_combined_analyses = []
        total_triggers = 0
        
        for i, chunk in enumerate(chunks):
            log(f"\n📝 Processing chunk {i+1}/{len(chunks)} ({len(chunk)} conversations)")

            chunk_results = self.analyze_conversation_chunk(chunk, logs, log_callback)
            
            all_combined_analyses.extend(chunk_results['combined_analyses'])
            total_triggers += chunk_results['emotional_triggers_found']
            
            log(f"   ✓ processed {chunk_results['conversations_processed']} conversations")
            log(f"   ✓ found {chunk_results['emotional_triggers_found']} emotional triggers")
        
        # Calculate final metrics
        # Derive simple meters from combined boolean flags to keep UI familiar
        snippy_count = sum(1 for a in all_combined_analyses if a.get('is_snippy'))
        hyperbolic_count = sum(1 for a in all_combined_analyses if a.get('is_hyperbolic'))
        total = max(1, len(all_combined_analyses))
        avg_snippy_score = round(10.0 * snippy_count / total, 2)
        avg_hyperbolic_score = round(10.0 * hyperbolic_count / total, 2)
        
        # Determine levels
        snippy_level = 'high' if avg_snippy_score >= 7 else 'medium' if avg_snippy_score >= 4 else 'low'
        hyperbolic_level = 'high' if avg_hyperbolic_score >= 7 else 'medium' if avg_hyperbolic_score >= 4 else 'low'
        
        # Get top examples
        snippy_examples = [a for a in all_combined_analyses if a.get('is_snippy')][:3]
        hyperbolic_examples = [a for a in all_combined_analyses if a.get('is_hyperbolic')][:3]
        
        return {
            'snippy_meter': {
                'score': round(avg_snippy_score, 2),
                'level': snippy_level,
                'total_analyses': len(all_combined_analyses),
                'high_score_count': len(snippy_examples),
                'examples': snippy_examples  # Up to 3 examples
            },
            'hyperbolic_meter': {
                'score': round(avg_hyperbolic_score, 2),
                'level': hyperbolic_level,
                'total_analyses': len(all_combined_analyses),
                'high_score_count': len(hyperbolic_examples),
                'examples': hyperbolic_examples  # Up to 3 examples
            },
            'combined_results': all_combined_analyses,
            'total_emotional_triggers': total_triggers,
            'total_conversations': len(conversations),
            'analysis_timestamp': datetime.datetime.now().isoformat(),
            'logs': logs
        }
    
    def get_personalized_insights(self, analysis_results: Dict[str, Any]) -> str:
        """Get personalized insights based on Gemma analysis"""
        prompt = f"""
        Based on this detailed analysis of Pruitt's communication patterns, provide specific insights:

        Snippy Response Analysis:
        - Average Score: {analysis_results['snippy_meter']['score']}/10
        - Level: {analysis_results['snippy_meter']['level']}
        - High score instances: {analysis_results['snippy_meter']['high_score_count']}

        Hyperbolic Language Analysis:
        - Average Score: {analysis_results['hyperbolic_meter']['score']}/10
        - Level: {analysis_results['hyperbolic_meter']['level']}
        - High score instances: {analysis_results['hyperbolic_meter']['high_score_count']}

        Please provide:
        1. Specific recommendations for improving communication
        2. Alternative phrases to use instead of snippy responses
        3. Ways to reduce hyperbolic language
        4. Communication techniques for more measured responses
        5. Warning signs to watch for in future conversations
        """
        
        try:
            if not self.memory_service._llm:
                return "LLM not available in memory service"

            response = self.memory_service._llm(
                prompt=prompt,
                max_tokens=512,
                temperature=0.7,
            )
            return response['choices'][0]['text'].strip()
                
        except Exception as e:
            return f"Analysis error: {str(e)}"

def main():
    """Test the Gemma context analyzer"""
    # This main function will not work without a running server providing the memory_service
    # It should be adapted for standalone testing if needed.
    print("Cannot run gemma_context_analyzer directly after refactoring.")
    print("Please test through the main3.py server endpoints.")


if __name__ == "__main__":
    main()
