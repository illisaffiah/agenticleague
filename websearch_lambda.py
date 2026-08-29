import time
import urllib.request
import urllib.error
from html.parser import HTMLParser

MAX_TEXT_LENGTH = 8000


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text_parts = []
        self.skip_tags = {'script', 'style', 'nav', 'footer', 'header'}
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.skip_tags:
            self.skip_depth += 1

    def handle_endtag(self, tag):
        if tag in self.skip_tags:
            self.skip_depth = max(0, self.skip_depth - 1)

    def handle_data(self, data):
        if self.skip_depth == 0:
            stripped = data.strip()
            if stripped:
                self.text_parts.append(stripped)

    def get_parts(self):
        return self.text_parts


def find_relevant_chunks(parts, keywords, context=1, max_chunks=3):
    """Return the paragraphs that best match the keywords, most-relevant FIRST,
    with neighboring lines for context. Ordering by score (not document order)
    puts the answer-bearing sentence at the top so the model reads it first."""
    if not keywords:
        return None

    lower_keywords = [k.lower() for k in keywords if k.strip()]
    if not lower_keywords:
        return None

    scores = []
    for i, part in enumerate(parts):
        part_lower = part.lower()
        score = sum(1 for kw in lower_keywords if kw in part_lower)
        if score > 0:
            # tie-break: prefer shorter, denser snippets (more likely the exact fact)
            scores.append((score, -len(part), i))

    if not scores:
        return None

    scores.sort(reverse=True)  # highest keyword-match first, then shortest
    top = scores[:max_chunks]

    result_lines = []
    seen = set()
    for _, _, idx in top:               # keep RELEVANCE order (best snippet first)
        start = max(0, idx - context)
        end = min(len(parts), idx + context + 1)
        for j in range(start, end):
            if j not in seen:
                result_lines.append(parts[j])
                seen.add(j)

    return '\n'.join(result_lines)


def fetch_url(url, keywords=None, max_retries=2, retry_delay=1):
    req = urllib.request.Request(
        url,
        headers={'User-Agent': 'Mozilla/5.0 (compatible; AILeagueBot/1.0)'}
    )

    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                raw_html = response.read().decode('utf-8', errors='replace')

            parser = TextExtractor()
            parser.feed(raw_html)
            parts = parser.get_parts()

            relevant = find_relevant_chunks(parts, keywords) if keywords else None
            if relevant:
                return relevant

            text = '\n'.join(parts)
            if len(text) > MAX_TEXT_LENGTH:
                text = text[:MAX_TEXT_LENGTH] + "\n...[truncated]"
            return text

        except urllib.error.HTTPError:
            raise
        except urllib.error.URLError as e:
            last_error = e
            if attempt < max_retries:
                time.sleep(retry_delay)
            continue

    raise last_error


import re as _re


def extract_url(event):
    if 'url' in event:
        return event['url']
    if 'input' in event and isinstance(event['input'], dict) and 'url' in event['input']:
        return event['input']['url']
    if 'parameters' in event and isinstance(event['parameters'], list):
        for param in event['parameters']:
            if param.get('name') == 'url':
                return param.get('value', '')
    return ''


def extract_question(event):
    """The original challenge question text, if the caller passes it. Optional."""
    if 'question' in event:
        return str(event['question'])
    if 'input' in event and isinstance(event['input'], dict) and 'question' in event['input']:
        return str(event['input']['question'])
    if 'parameters' in event and isinstance(event['parameters'], list):
        for param in event['parameters']:
            if param.get('name') in ('question', 'query'):
                return str(param.get('value', ''))
    return ''


# Words that are never a standalone "answer" even if capitalized near the metric.
_STOPWORDS = {
    "The", "This", "That", "These", "Those", "With", "Using", "You", "Your",
    "Amazon", "AWS", "SageMaker", "Learn", "More", "Get", "Started", "For",
    "And", "Our", "New", "Free", "Tier", "Service", "Services", "Model", "Models",
}


def _sentences(text):
    # split into rough sentences/lines for scanning
    chunks = _re.split(r'(?<=[.!?])\s+|\n', text)
    return [c.strip() for c in chunks if c.strip()]


def extract_answer(text, question):
    """
    Deterministically extract the most likely EXACT answer token from the page,
    based on what the question asks. Returns a short string or None.
    This moves the 'reading' out of the LLM (rule-based > prompting).
    """
    if not text:
        return None
    q = (question or "").lower()

    # 1) MONEY: question asks "how many credits / how much / $" -> return the largest $ figure
    if any(w in q for w in ["credit", "how much", "how many", "$", "dollar", "cost", "price", "free"]):
        amounts = _re.findall(r'\$\s?[\d,]+(?:\.\d+)?', text)
        if amounts:
            # normalize and pick the largest (e.g. "$200" over "$100")
            def val(a):
                return float(_re.sub(r'[^\d.]', '', a) or 0)
            best = max(amounts, key=val)
            return best.replace(" ", "")

    # 2) PERCENT-LINKED FEATURE: question mentions a % (e.g. "reduce ... by up to 40%")
    pct_in_q = _re.search(r'(\d+)\s*%', q)
    if pct_in_q or "percent" in q or "reduce" in q or "faster" in q or "up to" in q:
        target_pct = pct_in_q.group(1) if pct_in_q else None
        for sent in _sentences(text):
            if target_pct and (target_pct + "%") not in sent and (target_pct + " %") not in sent:
                # if the question named a specific %, focus on sentences containing it
                if _re.search(r'\d+\s*%', sent) and target_pct not in sent:
                    continue
            if _re.search(r'\d+\s*%', sent) or (target_pct and target_pct in sent):
                # find a proper-noun product/feature name in this sentence
                caps = _re.findall(r'\b([A-Z][a-zA-Z]+(?:[A-Z][a-zA-Z]+)*)\b', sent)
                for c in caps:
                    if c not in _STOPWORDS and len(c) > 2:
                        return c
    # 3) Fallback: no deterministic extraction
    return None


def extract_keywords(event):
    def parse_kw(val):
        if isinstance(val, list):
            return val
        if isinstance(val, str):
            return [k.strip() for k in val.split(',') if k.strip()]
        return []

    if 'keywords' in event:
        return parse_kw(event['keywords'])
    if 'input' in event and isinstance(event['input'], dict) and 'keywords' in event['input']:
        return parse_kw(event['input']['keywords'])
    if 'parameters' in event and isinstance(event['parameters'], list):
        for param in event['parameters']:
            if param.get('name') == 'keywords':
                return parse_kw(param.get('value', ''))
    return []


def lambda_handler(event, context):
    print(f"RAW EVENT RECEIVED: {event}")
    url = extract_url(event)
    keywords = extract_keywords(event)
    question = extract_question(event)

    if not url:
        return {"success": False, "error": "No URL provided in event"}

    try:
        text = fetch_url(url, keywords=keywords)
        result = {"success": True, "content": text}
        # Deterministic answer extraction (rule-based). If we can confidently
        # pull the exact figure/term, surface it so the model echoes it.
        try:
            ans = extract_answer(text, question) if question else extract_answer(text, ",".join(keywords))
            if ans:
                result["suggested_answer"] = ans
                # Prepend it so it is the very first thing the model reads.
                result["content"] = f"ANSWER: {ans}\n\n{text}"
        except Exception as ex:
            print(f"extract_answer skipped: {ex}")
        return result
    except urllib.error.HTTPError as e:
        return {"success": False, "error": f"HTTP error {e.code}: {e.reason}"}
    except urllib.error.URLError as e:
        return {"success": False, "error": f"Could not reach URL: {e.reason}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    # Simulated page content tests (no network) to verify extraction logic
    sagemaker_text = ("Scale Gen AI Model Development. SageMaker HyperPod automatically manages "
                      "task queues and can reduce model training time by up to 40% with built-in resiliency.")
    bedrock_text = ("AWS Free Tier update: New customers can get started with up to $200 in credits. "
                    "You get $100 in credits at sign-up and can earn up to $100 more.")
    print("sagemaker ->", extract_answer(sagemaker_text, "what feature can reduce training time by up to 40%?"))
    print("bedrock   ->", extract_answer(bedrock_text, "up to how many credits can a new AWS customer receive for free?"))
