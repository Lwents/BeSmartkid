import json
import math
import re


def parse_ai_questions(raw_text):
    """Extract question objects even when the provider wraps or partially truncates JSON."""
    raw = (raw_text or "").strip()
    if not raw:
        return []
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\s*```$", "", raw).strip()

    values = []
    for candidate in _json_candidates(raw):
        try:
            values.append(json.loads(candidate))
        except (TypeError, ValueError):
            continue
    if not values:
        values.extend(_scan_complete_json_values(raw))

    questions = []
    for value in values:
        questions.extend(_question_objects(value))
    return questions


def normalize_ai_questions(candidates, seen_prompts=None, limit=None):
    seen = seen_prompts if seen_prompts is not None else set()
    result = []
    for candidate in candidates or []:
        normalized = _normalize_question(candidate)
        if normalized is None:
            continue
        prompt_key = _normalized_text(normalized["text"])
        if prompt_key in seen:
            continue
        seen.add(prompt_key)
        result.append(normalized)
        if limit is not None and len(result) >= limit:
            break
    return result


def _json_candidates(raw):
    candidates = [raw]
    object_start, object_end = raw.find("{"), raw.rfind("}")
    if object_start >= 0 and object_end > object_start:
        candidates.append(raw[object_start: object_end + 1])
    array_start, array_end = raw.find("["), raw.rfind("]")
    if array_start >= 0 and array_end > array_start:
        candidates.append(raw[array_start: array_end + 1])
    return list(dict.fromkeys(candidates))


def _scan_complete_json_values(raw):
    decoder = json.JSONDecoder()
    values = []
    index = 0
    while index < len(raw):
        match = re.search(r"[\[{]", raw[index:])
        if match is None:
            break
        start = index + match.start()
        try:
            value, end = decoder.raw_decode(raw, start)
            values.append(value)
            index = end
        except ValueError:
            index = start + 1
    return values


def _question_objects(value):
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if not isinstance(value, dict):
        return []
    questions = value.get("questions")
    if isinstance(questions, list):
        return [item for item in questions if isinstance(item, dict)]
    if any(key in value for key in ("text", "prompt", "question", "content")):
        return [value]
    return []


def _normalize_question(source):
    if not isinstance(source, dict):
        return None
    prompt = _first_text(source, "text", "prompt", "question", "content")
    if not prompt:
        return None

    question_type = _first_text(source, "type", "question_type", "kind").lower()
    is_boolean = question_type in {"boolean", "bool", "true_false", "true-false"}
    raw_choices = source.get("choices")
    if not isinstance(raw_choices, list):
        raw_choices = source.get("options")
    if not isinstance(raw_choices, list):
        raw_choices = source.get("answers")

    if is_boolean and not isinstance(raw_choices, list):
        correct = _as_boolean(source.get("correct_answer"))
        if correct is None:
            correct = _as_boolean(source.get("answer"))
        if correct is None:
            return None
        return {
            "type": "boolean",
            "text": prompt,
            "score": _score(source),
            "choices": ["Đúng", "Sai"],
            "correct_indices": [0 if correct else 1],
        }

    if not isinstance(raw_choices, list):
        return None

    requested_correct = _correct_index(source, raw_choices)
    choices = []
    index_map = {}
    seen_choices = set()
    for original_index, raw_choice in enumerate(raw_choices):
        choice_text = _choice_text(raw_choice)
        choice_key = _normalized_text(choice_text)
        if not choice_text or choice_key in seen_choices or len(choices) >= 6:
            continue
        seen_choices.add(choice_key)
        index_map[original_index] = len(choices)
        choices.append(choice_text)
    if len(choices) < 2 or requested_correct not in index_map:
        return None

    return {
        "type": "single",
        "text": prompt,
        "score": _score(source),
        "choices": choices,
        "correct_indices": [index_map[requested_correct]],
    }


def _correct_index(source, choices):
    for key in ("correct_indices", "correctIndexes", "correct_indexes"):
        values = source.get(key)
        if isinstance(values, list) and values:
            parsed = _as_int(values[0])
            if parsed is not None:
                return parsed
    for key in ("correct_index", "correctIndex", "answer_index", "answerIndex"):
        parsed = _as_int(source.get(key))
        if parsed is not None:
            return parsed
    for index, choice in enumerate(choices):
        if isinstance(choice, dict) and (
            choice.get("is_correct") is True or choice.get("correct") is True
        ):
            return index

    answer = source.get("correct_answer", source.get("answer"))
    parsed = _as_int(answer)
    if parsed is not None and 0 <= parsed < len(choices):
        return parsed
    if isinstance(answer, str):
        stripped = answer.strip()
        if len(stripped) == 1 and stripped.upper() in "ABCDEF":
            return ord(stripped.upper()) - ord("A")
        answer_key = _normalized_text(stripped)
        for index, choice in enumerate(choices):
            if _normalized_text(_choice_text(choice)) == answer_key:
                return index
    return None


def _choice_text(value):
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return _first_text(value, "text", "label", "content", "value")
    return ""


def _first_text(source, *keys):
    for key in keys:
        value = source.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _normalized_text(value):
    return " ".join((value or "").lower().split())


def _as_int(value):
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_boolean(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "đúng", "dung", "yes", "1"}:
            return True
        if normalized in {"false", "sai", "no", "0"}:
            return False
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    return None


def _score(source):
    raw = source.get("score", source.get("points", 1))
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 1
    if not math.isfinite(value) or value <= 0:
        return 1
    return int(value) if value.is_integer() else value
