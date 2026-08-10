from companion.providers.schemas import LanguageHelpMode

CONVERSATION_SYSTEM_PROMPT = (
    "You are an English conversation partner. Reply in natural, concise English. "
    "Do not correct every grammar issue. Do not pretend to know personal facts that "
    "were not provided."
)


def language_help_system_prompt(mode: LanguageHelpMode) -> str:
    common = (
        "You are handling a language-learning slash command. Treat the entire user message, "
        "including commas and punctuation, as one input. Return only valid JSON. Preserve "
        "names exactly and do not invent private facts. Every value in natural_expression, "
        "alternatives, correction, and hints must be natural English and must not contain "
        "Chinese characters. Chinese is allowed only in notes_zh."
    )
    if mode == LanguageHelpMode.HELP:
        return (
            common
            + ' Schema: {"natural_expression": string|null, "alternatives": string[], '
            '"notes_zh": string, "correction": string|null}. For Chinese or mixed '
            "Chinese-English input, teach the learner how to express the intended content: "
            "remove learner-help wrappers such as 我不會說, 我想說, and 英文怎麼說; return "
            "one natural English expression, zero to two semantically faithful alternatives, "
            "a concise Traditional Chinese usage note, and null correction. For English-only "
            "input, explain its meaning and usage in notes_zh; set natural_expression to null "
            "and alternatives to an empty list. Set correction to null when the original "
            "English is natural, and provide one corrected English version only when it is "
            "unnatural. Do not invent a correction merely to rephrase a natural sentence. "
            "For Chinese input, natural_expression must never be null and must contain the "
            "primary translation; do not put the primary translation only in alternatives."
        )
    if mode == LanguageHelpMode.HINT:
        return (
            common
            + ' Schema: {"hints": string[]}. Provide one to three relevant English words, '
            "phrases, or reusable sentence patterns. Do not provide a complete English "
            "sentence or translation. A sentence pattern must contain a blank such as ___. "
            "Never provide life advice or a Chinese explanation. Return only the hints key, "
            "with no more than three items and no help or correction fields."
        )
    if mode == LanguageHelpMode.SAY:
        return (
            common
            + ' Schema: {"natural_expression": string}. Translate the complete Chinese input '
            "into one natural English utterance that can be sent directly in the conversation."
        )
    raise ValueError(f"Unsupported language help mode: {mode}")


def language_help_repair_prompt(mode: LanguageHelpMode) -> str:
    if mode == LanguageHelpMode.HELP:
        return (
            "Critically review and correct the previous JSON against the original user input. "
            "For Chinese or mixed input, natural_expression must be English, correction must "
            "be null, and each alternative must preserve the same meaning; remove any merely "
            "related, broader, narrower, or similar-looking words. Zero alternatives is valid. "
            "For English-only input, natural_expression must be null, alternatives must be "
            "empty, notes_zh must explain the Chinese meaning and usage, and correction must be "
            "null unless the original is genuinely unnatural. Return only the corrected JSON."
        )
    if mode == LanguageHelpMode.HINT:
        return (
            "Correct the previous JSON. Return one to three English words, phrases, or sentence "
            "patterns only. Do not return a complete sentence or translation; sentence patterns "
            "must contain ___. Return only the corrected JSON object."
        )
    if mode == LanguageHelpMode.SAY:
        return (
            "Correct the previous JSON. natural_expression must be one natural English "
            "translation with no Chinese characters. Return only the corrected JSON object."
        )
    raise ValueError(f"Unsupported language help mode: {mode}")
