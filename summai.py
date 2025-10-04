
from typing import Optional
import logging

logger = logging.getLogger(__name__)

_summarizer = None

def _get_summarizer():
    global _summarizer
    if _summarizer is not None:
        return _summarizer
    try:
        from transformers import pipeline
        _summarizer = pipeline("summarization", model="facebook/bart-large-cnn")
        return _summarizer
    except Exception as e:
        logger.exception("summarizer load failed: %s", e)
        _summarizer = None
        return None

def summarize_text(text: str, max_new_tokens: int = 256, min_length: int = 30, ratio: float = 0.35) -> str:

    if not text:
        return ""

    try:
        s = _get_summarizer()
        if s is None:
            return text

        
        try:
            from transformers import logging as hf_logging
            hf_logging.set_verbosity_error()
        except Exception:
            import logging
            logging.getLogger("transformers").setLevel(logging.ERROR)
            logging.getLogger("transformers.generation_utils").setLevel(logging.ERROR)

        tokenizer = getattr(s, "tokenizer", None)

        def token_len(t: str) -> int:
            try:
                if tokenizer is not None:
                    
                    if hasattr(tokenizer, "encode"):
                        return len(tokenizer.encode(t))
                    
                    enc = tokenizer(t, return_tensors="pt", truncation=False)
                    return int(enc["input_ids"].shape[1])
            except Exception:
                pass
            
            return max(1, len(t.split()))

        def suggest_tokens(inp_len: int) -> int:
            suggested = max(min_length, max(10, int(inp_len * ratio)))
            return min(suggested, max_new_tokens)

        
        if len(text) > 1000:
            chunks = []
            start = 0
            while start < len(text):
                chunks.append(text[start:start + 900])
                start += 900

            summaries = []
            for c in chunks:
                inp_len = token_len(c)
                suggested = suggest_tokens(inp_len)
                
                try:
                    if hasattr(s, "model") and hasattr(s.model, "config"):
                        s.model.config.max_length = inp_len + suggested
                except Exception:
                    pass

                out = s(c, max_new_tokens=suggested, min_length=min_length, do_sample=False)
                summaries.append(out[0].get('summary_text', ''))

            joined = " ".join([t for t in summaries if t])
            if not joined:
                return " ".join(summaries) or text

            inp_len = token_len(joined)
            suggested = suggest_tokens(inp_len)
            try:
                if hasattr(s, "model") and hasattr(s.model, "config"):
                    s.model.config.max_length = inp_len + suggested
            except Exception:
                pass

            final = s(joined, max_new_tokens=suggested, min_length=min_length, do_sample=False)
            return final[0].get('summary_text', joined)

        
        inp_len = token_len(text)
        suggested = suggest_tokens(inp_len)
        try:
            if hasattr(s, "model") and hasattr(s.model, "config"):
                s.model.config.max_length = inp_len + suggested
        except Exception:
            pass

        out = s(text, max_new_tokens=suggested, min_length=min_length, do_sample=False)
        return out[0].get('summary_text', text)

    except Exception as e:
        logger.exception("summarization error: %s", e)
        return text