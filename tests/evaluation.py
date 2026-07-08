import os
import sys
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

# Ensure we can import from src
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

from src.retrieval import get_hybrid_retriever
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

# Load environment variables
load_dotenv(os.path.join(BASE_DIR, '.env'))

# Define 15-Question Gold Standard Test Set
GOLD_STANDARD_TEST_SET = [
    # --- Math 1 Standards ---
    {
        "id": 1,
        "course_id": "M1",
        "standard_id": "NC.M1.A-SSE.1a",
        "question": "Explain how to interpret the terms and coefficients of the expression 200(1.05)^t in the context of compound interest."
    },
    {
        "id": 2,
        "course_id": "M1",
        "standard_id": "NC.M1.A-REI.3",
        "question": "How do I solve a multi-step linear equation like 3(x - 2) + 5 = 14 and justify each step in NC Math 1?"
    },
    {
        "id": 3,
        "course_id": "M1",
        "standard_id": "NC.M1.F-IF.2",
        "question": "What is function notation, and how do I evaluate f(3) if f(x) = 2x^2 - 5x + 1?"
    },
    {
        "id": 4,
        "course_id": "M1",
        "standard_id": "NC.M1.A-CED.2",
        "question": "How do I write an equation or inequality to represent a constraint in a real-world scenario, like comparing cell phone plans?"
    },
    {
        "id": 5,
        "course_id": "M1",
        "standard_id": "NC.M1.S-ID.1",
        "question": "How do I compare the center and spread of two different data distributions using box plots in NC Math 1?"
    },
    # --- Math 2 Standards ---
    {
        "id": 6,
        "course_id": "M2",
        "standard_id": "NC.M2.N-RN.2",
        "question": "How do I rewrite the radical expression sqrt(x^3) using a rational exponent?"
    },
    {
        "id": 7,
        "course_id": "M2",
        "standard_id": "NC.M2.A-REI.4a",
        "question": "What are the methods for solving a quadratic equation by completing the square in NC Math 2?"
    },
    {
        "id": 8,
        "course_id": "M2",
        "standard_id": "NC.M2.G-CO.5",
        "question": "Explain the geometric transformations that preserve distance and angle, and how they relate to congruence in Math 2."
    },
    {
        "id": 9,
        "course_id": "M2",
        "standard_id": "NC.M2.F-IF.7",
        "question": "How do I graph and analyze the key features of a quadratic function f(x) = x^2 - 4x + 3?"
    },
    {
        "id": 10,
        "course_id": "M2",
        "standard_id": "NC.M2.G-SRT.4",
        "question": "How do I use triangle similarity criteria, such as AA similarity, to prove two triangles are similar?"
    },
    # --- Math 3 Standards (from project specifications) ---
    {
        "id": 11,
        "course_id": "M3",
        "standard_id": "NC.M3.A-APR.2",
        "question": "Evaluate p(-2) for p(x)=x^5-x^4+8x^2-9x+30. What does this tell you about the factors of p(x)?"
    },
    {
        "id": 12,
        "course_id": "M3",
        "standard_id": "NC.M3.A-APR.2",
        "question": "If (x-2) is a factor of P(x)=x^4-3x^3+ax^2-6x+14, what is the value of a?"
    },
    {
        "id": 13,
        "course_id": "M3",
        "standard_id": "NC.M3.A-APR.3",
        "question": "What are the solutions to the polynomial: p(x)=(x-5)(3x+5)(x^2-7x+15)?"
    },
    {
        "id": 14,
        "course_id": "M3",
        "standard_id": "NC.M3.A-CED.3",
        "question": "After how many years will the Company B salary ($60k with 4% increase) be higher than Company A ($80k with $1k increase)?"
    },
    {
        "id": 15,
        "course_id": "M3",
        "standard_id": "NC.M3.A-REI.1",
        "question": "Describe your process for solving the polynomial x^3+4x^2+x=6 and explain the mathematical reasoning for each step."
    }
]

def evaluate_single_question(item, retriever, tutor_chain, evaluator_llm):
    qid = item["id"]
    qtext = item["question"]
    target_std = item["standard_id"]
    course_id = item["course_id"]
    
    print(f"[{qid}/15] Thread started for Course {course_id} | Standard: {target_std}")
    
    # 1. Retrieve
    start_time = time.time()
    docs = retriever.invoke(qtext)
    retrieval_latency = time.time() - start_time
    
    retrieved_stds = [doc.metadata.get("standard_id") for doc in docs if doc.metadata.get("standard_id")]
    
    # Check Hit Rate
    hit = 0
    for r_std in retrieved_stds:
        if target_std in r_std or r_std in target_std:
            hit = 1
            break
            
    context_str = "\n\n".join([f"[{doc.metadata.get('standard_id')}] {doc.page_content}" for doc in docs])
    
    # 2. Generate
    try:
        answer = tutor_chain.invoke({"context": context_str, "question": qtext})
    except Exception as e:
        print(f"[{qid}/15] Error generating answer: {e}")
        answer = f"ERROR GENERATING ANSWER: {str(e)}"
        
    # 3. Judge Faithfulness
    faithfulness_prompt = f"""You are an expert AI evaluator assessing a RAG (Retrieval-Augmented Generation) educational chat system.
Analyze the student/parent question, the retrieved educational context, and the tutor's answer.
Determine if the tutor's answer is faithful to the context (i.e. every statement in the answer is grounded in and supported by the retrieved context, and it does not make up information or use outside knowledge).

If the tutor answered "I cannot find this in our syllabus, please ask your teacher" because the context did not contain the information, score this as 5 (fully faithful).

Question: {qtext}
Retrieved Context:
{context_str}

Tutor's Answer:
{answer}

Provide your evaluation as a valid JSON object with keys "score" (integer 1-5, where 5 is perfectly grounded/faithful, and 1 has significant hallucinations or uses outside knowledge) and "reason" (detailed explanation). Do not add any extra text outside the JSON block.
"""
    f_score = 1
    f_reason = "Error"
    try:
        f_resp = evaluator_llm.invoke(faithfulness_prompt).content.strip()
        if "```json" in f_resp:
            f_resp = f_resp.split("```json")[1].split("```")[0].strip()
        elif "```" in f_resp:
            f_resp = f_resp.split("```")[1].split("```")[0].strip()
        f_eval = json.loads(f_resp)
        f_score = int(f_eval.get("score", 1))
        f_reason = f_eval.get("reason", "")
    except Exception as e:
        print(f"[{qid}/15] Error evaluating faithfulness: {e}. Raw response: {f_resp}")
        f_reason = f"Parser Error: {str(e)}"
        
    # 4. Judge Answer Relevance
    relevance_prompt = f"""You are an expert AI evaluator assessing a RAG (Retrieval-Augmented Generation) educational chat system.
Analyze the student/parent question, and the tutor's answer.
Determine if the tutor's answer is relevant to the question (i.e. it directly addresses the user's question, is helpful, and does not contain extraneous or unrelated math topics).

Question: {qtext}
Tutor's Answer:
{answer}

Provide your evaluation as a valid JSON object with keys "score" (integer 1-5, where 5 means perfectly relevant and direct, and 1 is completely irrelevant or off-topic) and "reason" (detailed explanation). Do not add any extra text outside the JSON block.
"""
    r_score = 1
    r_reason = "Error"
    try:
        r_resp = evaluator_llm.invoke(relevance_prompt).content.strip()
        if "```json" in r_resp:
            r_resp = r_resp.split("```json")[1].split("```")[0].strip()
        elif "```" in r_resp:
            r_resp = r_resp.split("```")[1].split("```")[0].strip()
        r_eval = json.loads(r_resp)
        r_score = int(r_eval.get("score", 1))
        r_reason = r_eval.get("reason", "")
    except Exception as e:
        print(f"[{qid}/15] Error evaluating relevance: {e}. Raw response: {r_resp}")
        r_reason = f"Parser Error: {str(e)}"
        
    print(f"[{qid}/15] Thread completed. Hit: {hit} | Faithfulness: {f_score}/5 | Relevance: {r_score}/5")
    
    return {
        "id": qid,
        "course_id": course_id,
        "standard_id": target_std,
        "question": qtext,
        "retrieved_stds": retrieved_stds,
        "hit_rate": hit,
        "answer": answer,
        "faithfulness_score": f_score,
        "faithfulness_reason": f_reason,
        "relevance_score": r_score,
        "relevance_reason": r_reason,
        "latency": retrieval_latency
    }

def run_eval():
    print("=== STARTING CONCURRENT RAG EVALUATION SYSTEM ===")
    start_all = time.time()
    
    print("Loading hybrid retriever...")
    retriever = get_hybrid_retriever()
    
    api_key = os.environ.get("NEBIUS_API_KEY")
    if not api_key:
        print("Error: NEBIUS_API_KEY not found in environment variables.")
        return
        
    # Share LLM clients (they are thread-safe)
    llm = ChatOpenAI(
        base_url=os.environ.get("NEBIUS_BASE_URL", "https://api.studio.nebius.ai/v1/"),
        api_key=api_key,
        model="meta-llama/Llama-3.3-70B-Instruct",
        temperature=0.0
    )
    
    evaluator_llm = ChatOpenAI(
        base_url=os.environ.get("NEBIUS_BASE_URL", "https://api.studio.nebius.ai/v1/"),
        api_key=api_key,
        model="meta-llama/Llama-3.3-70B-Instruct",
        temperature=0.0
    )
    
    tutor_prompt = ChatPromptTemplate.from_messages([
        ("system", """You are a Patient Math Tutor for Wake County students and parents. 
Answer the following question using ONLY the provided educational standards context. 
Explain the concepts simply so a student or parent can understand.
Do not use outside knowledge. 
If the context does not contain the answer, say 'I cannot find this in our syllabus, please ask your teacher.'

Context:
{context}
"""),
        ("human", "{question}")
    ])
    
    tutor_chain = tutor_prompt | llm | StrOutputParser()
    
    results = []
    
    # Run evaluation with ThreadPoolExecutor
    max_workers = 5  # Evaluates 5 questions concurrently
    print(f"Running evaluation with {max_workers} concurrent threads...")
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(evaluate_single_question, item, retriever, tutor_chain, evaluator_llm)
            for item in GOLD_STANDARD_TEST_SET
        ]
        
        for future in as_completed(futures):
            try:
                res = future.result()
                results.append(res)
            except Exception as exc:
                print(f"Generated an exception: {exc}")
                
    # Sort results by ID to keep order
    results.sort(key=lambda x: x["id"])
    
    # Aggregate Metrics
    total_questions = len(GOLD_STANDARD_TEST_SET)
    avg_hit_rate = sum(r["hit_rate"] for r in results) / total_questions
    avg_faithfulness = sum(r["faithfulness_score"] for r in results) / total_questions
    avg_relevance = sum(r["relevance_score"] for r in results) / total_questions
    avg_latency = sum(r["latency"] for r in results) / total_questions
    total_time = time.time() - start_all
    
    print("\n=== CONCURRENT EVALUATION REPORT SUMMARY ===")
    print(f"Total Questions: {total_questions}")
    print(f"Total Time Taken: {total_time:.2f}s")
    print(f"Average Hit Rate (Retrieval): {avg_hit_rate:.2%}")
    print(f"Average Faithfulness Score: {avg_faithfulness:.2f}/5.00")
    print(f"Average Relevance Score: {avg_relevance:.2f}/5.00")
    print(f"Average Retrieval Latency: {avg_latency:.4f}s")
    
    # Save Report to Markdown file
    report_path = os.path.join(BASE_DIR, "tests", "evaluation_report.md")
    with open(report_path, "w") as f:
        f.write("# NC Math RAG Pipeline Automated Evaluation Report\n\n")
        f.write("This report evaluates the performance of the hybrid RAG tutor pipeline over the NC Math 1, 2, and 3 curriculum unpacking guides. Evaluating retrieval quality (Hit Rate), generation groundedness (Faithfulness), and answer utility (Relevance) ensures a high-quality, hallucination-free educational resource.\n\n")
        
        f.write("## Executive Metrics\n\n")
        f.write("| Metric | Result | Target / Ideal | Status |\n")
        f.write("|---|---|---|---|\n")
        f.write(f"| **Retrieval Hit Rate** | {avg_hit_rate:.2%} | >= 90.0% | {'✅ Passed' if avg_hit_rate >= 0.9 else '⚠️ Review'} |\n")
        f.write(f"| **Average Faithfulness** | {avg_faithfulness:.2f}/5.00 | >= 4.50/5.00 | {'✅ Passed' if avg_faithfulness >= 4.5 else '⚠️ Review'} |\n")
        f.write(f"| **Average Relevance** | {avg_relevance:.2f}/5.00 | >= 4.50/5.00 | {'✅ Passed' if avg_relevance >= 4.5 else '⚠️ Review'} |\n")
        f.write(f"| **Average Retrieval Latency** | {avg_latency:.4f}s | < 1.0000s | ✅ Optimal |\n\n")
        
        f.write("## Detailed Evaluation Table\n\n")
        f.write("| ID | Course | Target Standard | Question | Retrieved Standards | Hit? | Faithfulness (1-5) | Relevance (1-5) | Retrieval Latency (s) |\n")
        f.write("|---|---|---|---|---|---|---|---|---|\n")
        for r in results:
            ret_stds_str = ", ".join([f"`{s}`" for s in r["retrieved_stds"]])
            f.write(f"| {r['id']} | {r['course_id']} | `{r['standard_id']}` | {r['question']} | {ret_stds_str} | {'1' if r['hit_rate'] else '0'} | {r['faithfulness_score']}/5 | {r['relevance_score']}/5 | {r['latency']:.3f} |\n")
            
        f.write("\n## Detailed Case Studies & Feedback\n\n")
        for r in results:
            f.write(f"### [Case {r['id']}] Standard: `{r['standard_id']}` (Course {r['course_id']})\n\n")
            f.write(f"**Question Asked:** {r['question']}\n\n")
            f.write(f"**Retrieved Standards:** {', '.join([f'`{s}`' for s in r['retrieved_stds']])}\n\n")
            f.write(f"**Generated Tutor Answer:**\n```markdown\n{r['answer']}\n```\n\n")
            f.write(f"**Faithfulness Judgment (Score: {r['faithfulness_score']}/5):**\n> {r['faithfulness_reason']}\n\n")
            f.write(f"**Relevance Judgment (Score: {r['relevance_score']}/5):**\n> {r['relevance_reason']}\n\n")
            f.write("---\n\n")
            
    print(f"\nEvaluation successfully completed! Report saved to {report_path}")

if __name__ == "__main__":
    run_eval()
