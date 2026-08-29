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
    """Return paragraphs matching the most keywords, with neighboring lines for context."""
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
            scores.append((score, i))

    if not scores:
        return None

    scores.sort(reverse=True)
    top_indices = sorted(i for _, i in scores[:max_chunks])

    result_lines = []
    seen = set()
    for idx in top_indices:
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

    if not url:
        return {"success": False, "error": "No URL provided in event"}

    try:
        text = fetch_url(url, keywords=keywords)
        # Opinion-based / source-attribution framing (Zhou et al. EMNLP 2023,
        # arXiv:2303.11315): presenting retrieved text as an explicit source
        # statement improves context-faithfulness and reduces the model
        # overriding it with parametric (memorized) knowledge.
        framed = ("The source web page states the following. Answer ONLY from "
                  "this text, quoting the exact number/term it gives:\n\n" + text)
        return {"success": True, "content": framed}
    except urllib.error.HTTPError as e:
        return {"success": False, "error": f"HTTP error {e.code}: {e.reason}"}
    except urllib.error.URLError as e:
        return {"success": False, "error": f"Could not reach URL: {e.reason}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    test_event = {"url": "https://aws.amazon.com/nova/forge/", "keywords": ["Nimbus Therapeutics", "20-50%"]}
    print(lambda_handler(test_event, None))
