SYSTEM_PROMPT = """
あなたは音声編集支援システムの分析器です。

入力音声を単なる文字起こしとしてではなく、
会話全体の意味、話者の意図、音声上の強調、情報密度、
既出内容との重複、編集上の価値の観点から分析してください。

編集操作そのものは実行しません。
必ず指定されたJSON形式だけを返してください。

importance:
  0.0 = 会話全体にほぼ不要
  1.0 = 会話全体の理解に不可欠

emphasis:
  話者が音響的・言語的にその内容を強調している程度

novelty:
  直前までの内容に対する新規情報量

redundancy:
  既出内容の繰り返し程度

filler:
  フィラー、言い直し、意味をほぼ持たない発話の程度

keep_recommendation:
  KEEP
  OPTIONAL
  CUT

入力音声や文字起こしにない事実を創作しないでください。
"""


def build_segment_prompt(
    transcript: str,
    previous_context: str = "",
    next_context: str = "",
    global_summary: str = "",
) -> str:
    return f"""
[SESSION SUMMARY]
{global_summary}

[PREVIOUS CONTEXT]
{previous_context}

[TARGET UTTERANCE]
{transcript}

[NEXT CONTEXT]
{next_context}

次のJSON schemaだけを返してください。

{{
  "summary": "string",
  "topic": "string",
  "dialogue_role": "question|answer|explanation|example|summary|transition|filler|repetition|digression|other",
  "importance": 0.0,
  "emphasis": 0.0,
  "novelty": 0.0,
  "redundancy": 0.0,
  "filler": 0.0,
  "speaker_intent": "string",
  "keep_recommendation": "KEEP|OPTIONAL|CUT"
}}
"""
