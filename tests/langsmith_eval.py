"""
Ed-Copilot LangSmith Evaluation
================================
Creates a LangSmith dataset from the gold-standard question set and runs an
LLM-as-judge experiment that shows up in the LangSmith UI with per-question
Faithfulness and Relevance scores.

Usage:
    python tests/langsmith_eval.py

Environment variables required:
    LANGCHAIN_API_KEY   — LangSmith API key
    NEBIUS_API_KEY      — Nebius LLM API key
"""

import os
import sys
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(BASE_DIR, ".env"))

os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
os.environ.setdefault("LANGCHAIN_PROJECT", "Ed-Copilot")

from langsmith import Client
from langsmith.evaluation import evaluate
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from src.orchestrator import build_graph, EdCopilotState
from src.district_registry import DistrictRegistry


DATASET_NAME = "Ed-Copilot Gold Standard Q&A"

GOLD_STANDARD_QUESTIONS = [
    {
        "id": 1,
        "course_id": "M1",
        "standard_id": "NC.M1.A-SSE.1a",
        "question": "Explain how to interpret the terms and coefficients of the expression 200(1.05)^t in the context of compound interest.",
        "district": "wake_county_nc",
        "persona": "student",
    },
    {
        "id": 2,
        "course_id": "M1",
        "standard_id": "NC.M1.A-REI.3",
        "question": "How do I solve a multi-step linear equation like 3(x - 2) + 5 = 14 and justify each step in NC Math 1?",
        "district": "wake_county_nc",
        "persona": "student",
    },
    {
        "id": 3,
        "course_id": "M1",
        "standard_id": "NC.M1.F-IF.2",
        "question": "What is function notation, and how do I evaluate f(3) if f(x) = 2x^2 - 5x + 1?",
        "district": "wake_county_nc",
        "persona": "student",
    },
    {
        "id": 4,
        "course_id": "M1",
        "standard_id": "NC.M1.A-CED.2",
        "question": "How do I write an equation or inequality to represent a constraint in a real-world scenario, like comparing cell phone plans?",
        "district": "wake_county_nc",
        "persona": "student",
    },
    {
        "id": 5,
        "course_id": "M1",
        "standard_id": "NC.M1.S-ID.1",
        "question": "How do I compare the center and spread of two different data distributions using box plots in NC Math 1?",
        "district": "wake_county_nc",
        "persona": "parent",
    },
    {
        "id": 6,
        "course_id": "M2",
        "standard_id": "NC.M2.N-RN.2",
        "question": "How do I rewrite the radical expression sqrt(x^3) using a rational exponent?",
        "district": "wake_county_nc",
        "persona": "student",
    },
    {
        "id": 7,
        "course_id": "M2",
        "standard_id": "NC.M2.A-REI.4a",
        "question": "What are the methods for solving a quadratic equation by completing the square in NC Math 2?",
        "district": "wake_county_nc",
        "persona": "student",
    },
    {
        "id": 8,
        "course_id": "M2",
        "standard_id": "NC.M2.G-CO.5",
        "question": "Explain the geometric transformations that preserve distance and angle, and how they relate to congruence in Math 2.",
        "district": "wake_county_nc",
        "persona": "student",
    },
    {
        "id": 9,
        "course_id": "M2",
        "standard_id": "NC.M2.F-IF.7",
        "question": "How do I graph and analyze the key features of a quadratic function f(x) = x^2 - 4x + 3?",
        "district": "wake_county_nc",
        "persona": "teacher",
    },
    {
        "id": 10,
        "course_id": "M2",
        "standard_id": "NC.M2.G-SRT.4",
        "question": "How do I use triangle similarity criteria, such as AA similarity, to prove two triangles are similar?",
        "district": "wake_county_nc",
        "persona": "student",
    },
    {
        "id": 11,
        "course_id": "M3",
        "standard_id": "NC.M3.A-APR.2",
        "question": "Evaluate p(-2) for p(x)=x^5-x^4+8x^2-9x+30. What does this tell you about the factors of p(x)?",
        "district": "wake_county_nc",
        "persona": "student",
    },
    {
        "id": 12,
        "course_id": "M3",
        "standard_id": "NC.M3.A-APR.2",
        "question": "If (x-2) is a factor of P(x)=x^4-3x^3+ax^2-6x+14, what is the value of a?",
        "district": "wake_county_nc",
        "persona": "student",
    },
    {
        "id": 13,
        "course_id": "M3",
        "standard_id": "NC.M3.A-APR.3",
        "question": "What are the solutions to the polynomial: p(x)=(x-5)(3x+5)(x^2-7x+15)?",
        "district": "wake_county_nc",
        "persona": "student",
    },
    {
        "id": 14,
        "course_id": "M3",
        "standard_id": "NC.M3.A-CED.3",
        "question": "After how many years will the Company B salary ($60k with 4% increase) be higher than Company A ($80k with $1k increase)?",
        "district": "wake_county_nc",
        "persona": "parent",
    },
    {
        "id": 15,
        "course_id": "M3",
        "standard_id": "NC.M3.A-REI.1",
        "question": "Describe your process for solving the polynomial x^3+4x^2+x=6 and explain the mathematical reasoning for each step.",
        "district": "wake_county_nc",
        "persona": "teacher",
    },
]


def get_or_create_dataset(client: Client) -> str:
    """Create the LangSmith dataset if it doesn't exist yet; return its name."""
    existing = [p.name for p in client.list_datasets()]
    if DATASET_NAME in existing:
        print(f"Dataset '{DATASET_NAME}' already exists — reusing it.")
        return DATASET_NAME

    print(f"Creating dataset '{DATASET_NAME}' in LangSmith...")
    dataset = client.create_dataset(
        dataset_name=DATASET_NAME,
        description=(
            "15 gold-standard questions covering NC Math 1, 2, and 3 curriculum standards. "
            "Used for LLM-as-judge evaluation of Ed-Copilot's math specialist."
        ),
    )
    examples = [
        {
            "inputs": {
                "question": q["question"],
                "district": q["district"],
                "persona": q["persona"],
                "standard_id": q["standard_id"],
                "course_id": q["course_id"],
            },
            "outputs": {
                "reference": (
                    f"A correct, curriculum-grounded answer about {q['standard_id']} "
                    f"from NC Math {q['course_id']}."
                )
            },
        }
        for q in GOLD_STANDARD_QUESTIONS
    ]
    client.create_examples(
        inputs=[e["inputs"] for e in examples],
        outputs=[e["outputs"] for e in examples],
        dataset_id=dataset.id,
    )
    print(f"Uploaded {len(examples)} examples to dataset.")
    return DATASET_NAME


def make_target(graph):
    """Return the target function that runs a single example through the orchestrator."""
    def target(inputs: dict) -> dict:
        state: EdCopilotState = {
            "messages": [{"role": "user", "content": inputs["question"]}],
            "persona": inputs.get("persona", "student"),
            "district": inputs.get("district", "wake_county_nc"),
            "intent": "",
            "context_docs": [],
            "response": "",
            "intent_badge": "",
        }
        result = graph.invoke(state)
        context_snippets = [
            f"[{doc.metadata.get('standard_id', 'N/A')}] {doc.page_content[:300]}"
            for doc in result.get("context_docs", [])
        ]
        return {
            "answer": result.get("response", ""),
            "intent": result.get("intent", ""),
            "context": "\n\n".join(context_snippets),
        }
    return target


def make_judge_llm():
    return ChatOpenAI(
        base_url=os.environ.get("NEBIUS_BASE_URL", "https://api.studio.nebius.ai/v1/"),
        api_key=os.environ.get("NEBIUS_API_KEY"),
        model=os.environ.get("NEBIUS_MODEL", "meta-llama/Llama-3.3-70B-Instruct"),
        temperature=0.0,
    )


def faithfulness_evaluator(inputs: dict, outputs: dict, reference_outputs: dict) -> dict:
    """
    LLM-as-judge: Is the answer grounded only in the retrieved curriculum context?
    Returns a score between 0.0 and 1.0 (normalized from 1-5).
    """
    question = inputs.get("question", "")
    answer = outputs.get("answer", "")
    context = outputs.get("context", "")

    if not answer:
        return {"key": "faithfulness", "score": 0.0, "comment": "Empty answer."}

    prompt = f"""You are an expert evaluator for an AI educational assistant.
Assess whether the tutor's answer is FAITHFUL to the retrieved curriculum context.
Faithful means: every claim in the answer is grounded in and supported by the context.
If the tutor said it could not find the answer in the syllabus, score this as 5 (fully faithful).

Question: {question}

Retrieved Context:
{context if context else "(no context retrieved)"}

Tutor's Answer:
{answer}

Return ONLY a valid JSON object with:
- "score": integer 1-5 (5 = perfectly grounded, 1 = significant hallucinations)
- "reason": one-sentence explanation
"""
    llm = make_judge_llm()
    try:
        raw = llm.invoke(prompt).content.strip()
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()
        result = json.loads(raw)
        score_1_5 = int(result.get("score", 1))
        normalized = (score_1_5 - 1) / 4.0
        return {
            "key": "faithfulness",
            "score": round(normalized, 2),
            "comment": result.get("reason", ""),
        }
    except Exception as e:
        return {"key": "faithfulness", "score": 0.0, "comment": f"Eval error: {e}"}


def relevance_evaluator(inputs: dict, outputs: dict, reference_outputs: dict) -> dict:
    """
    LLM-as-judge: Does the answer directly and helpfully address the student's question?
    Returns a score between 0.0 and 1.0 (normalized from 1-5).
    """
    question = inputs.get("question", "")
    answer = outputs.get("answer", "")

    if not answer:
        return {"key": "relevance", "score": 0.0, "comment": "Empty answer."}

    prompt = f"""You are an expert evaluator for an AI educational assistant.
Assess whether the tutor's answer is RELEVANT to the student's question.
Relevant means: it directly addresses what was asked, is helpful, and stays on topic.

Question: {question}

Tutor's Answer:
{answer}

Return ONLY a valid JSON object with:
- "score": integer 1-5 (5 = perfectly relevant, 1 = completely off-topic)
- "reason": one-sentence explanation
"""
    llm = make_judge_llm()
    try:
        raw = llm.invoke(prompt).content.strip()
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()
        result = json.loads(raw)
        score_1_5 = int(result.get("score", 1))
        normalized = (score_1_5 - 1) / 4.0
        return {
            "key": "relevance",
            "score": round(normalized, 2),
            "comment": result.get("reason", ""),
        }
    except Exception as e:
        return {"key": "relevance", "score": 0.0, "comment": f"Eval error: {e}"}


def retrieval_hit_evaluator(inputs: dict, outputs: dict, reference_outputs: dict) -> dict:
    """
    Checks whether the target standard ID was retrieved in the context docs.
    Returns 1.0 (hit) or 0.0 (miss).
    """
    target_std = inputs.get("standard_id", "")
    context = outputs.get("context", "")
    hit = target_std in context
    return {
        "key": "retrieval_hit",
        "score": 1.0 if hit else 0.0,
        "comment": f"Target standard '{target_std}' {'found' if hit else 'NOT found'} in retrieved context.",
    }


def main():
    api_key = os.environ.get("LANGCHAIN_API_KEY")
    if not api_key:
        print("ERROR: LANGCHAIN_API_KEY not set. Add it to your Replit secrets.")
        sys.exit(1)

    nebius_key = os.environ.get("NEBIUS_API_KEY")
    if not nebius_key:
        print("ERROR: NEBIUS_API_KEY not set.")
        sys.exit(1)

    print("=== Ed-Copilot LangSmith Evaluation ===\n")

    client = Client()
    dataset_name = get_or_create_dataset(client)

    print("\nLoading district registry...")
    registry = DistrictRegistry()

    print("Building orchestrator graph...")
    graph = build_graph(registry)

    target_fn = make_target(graph)

    print("\nRunning LangSmith evaluation experiment...")
    print("This will run all 15 questions through the full orchestrator + LLM-as-judge.")
    print("Results will appear in your LangSmith dashboard under the dataset.\n")

    results = evaluate(
        target_fn,
        data=dataset_name,
        evaluators=[
            faithfulness_evaluator,
            relevance_evaluator,
            retrieval_hit_evaluator,
        ],
        experiment_prefix="Ed-Copilot-Eval",
        description=(
            "Full orchestrator evaluation: intent routing → math specialist → "
            "LLM-as-judge scoring for Faithfulness, Relevance, and Retrieval Hit Rate."
        ),
        max_concurrency=3,
    )

    print("\n=== Evaluation complete! ===")
    print(f"View results at: https://smith.langchain.com")
    print(f"Project: {os.environ.get('LANGCHAIN_PROJECT', 'Ed-Copilot')}")
    print(f"Dataset: {dataset_name}")

    df = results.to_pandas()
    numeric_cols = [c for c in df.columns if "score" in c.lower()]
    if numeric_cols:
        print("\nAggregate scores:")
        for col in numeric_cols:
            vals = df[col].dropna()
            if len(vals):
                print(f"  {col}: {vals.mean():.2f} (avg over {len(vals)} examples)")


if __name__ == "__main__":
    main()
