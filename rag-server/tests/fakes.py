import hashlib
import math
import re


class FakeEmbeddings:
    """Only test fixtures use deterministic feature hashing; production always uses the local model."""

    calls = 0
    max_tokens = 220

    def texts(self, texts):
        self.calls += len(texts)
        result = []
        for text in texts:
            vector = [0.0] * 384
            for word in re.findall(r"\w+", text.lower()):
                index = int(hashlib.sha256(word.encode()).hexdigest()[:8], 16) % 384
                vector[index] += 1
            norm = math.sqrt(sum(value * value for value in vector)) or 1
            result.append([value / norm for value in vector])
        return result

    def query(self, text):
        return self.texts([text])[0]

    def token_count(self, text):
        return len(text.split())

    def token_parts(self, text, max_tokens=None):
        words = text.split()
        limit = max_tokens or self.max_tokens
        return [" ".join(words[i : i + limit]) for i in range(0, len(words), limit)]
