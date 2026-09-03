"""Prompt construction for test-case translation.

Builds the system + task + few-shot + conventions prompt that teaches a
local model (8B, tight context budget) to map a test-suite table into the
Pydantic TestCase JSON shape. The Expected Schema narration is copied
verbatim to schema_narration -- never converted to JSON Schema (PLAN 6.2).
"""

from __future__ import annotations

import json

_SYSTEM_PROMPT = (
    "Kamu adalah penerjemah test case API yang teliti. Kamu mengonversi satu "
    "tabel dari dokumen test suite standar menjadi satu objek JSON test case. "
    "Kamu TIDAK PERNAH mengarang nilai: salin apa yang tertulis, petakan "
    "secara tepat, dan terjemahkan label field bila perlu. Kamu TIDAK PERNAH "
    "menentukan lulus/gagal."
)

# One concrete labelled example giving the model a strong anchor.
_FEW_SHOT = """
Contoh:
[Test Case TC-001]
ID: TC-001
Judul: Validasi Response Login
Metode: POST
Path: /api/v1/auth/login
Headers:
Accept: application/json
Body (JSON): {"username": "admin", "password": "secret123"}
Expected Status Code: 200
Expected Schema: Response harus memuat field: access_token (string), token_type (string)

{"id": "TC-001", "title": "Validasi Response Login", "summary": null, "request": {"method": "POST", "path": "/api/v1/auth/login", "headers": {"Accept": "application/json"}, "query": {}, "body": {"username": "admin", "password": "secret123"}}, "expected": {"status": 200, "schema_narration": "Response harus memuat field: access_token (string), token_type (string)"}, "needs_review": false, "review_reason": null}
""".strip()

_CONVENTIONS = """
Konvensi:
- ID memakai pola TC-000 (3 digit).
- Method HANYA salah satu dari: GET, POST, PUT, PATCH, DELETE.
    Jika dokumen menulis method yang tidak termasuk daftar itu (misal TRACE,
    atau kosong): set "needs_review": true, isi review_reason yang menyebut
    method asli dari dokumen, DAN pilih method valid yang paling mendekati
    supaya test case tetap bisa dijalankan (GET/POST/PUT/PATCH/DELETE). Jangan
    pernah mengosongkan method.
- Path harus diawali dengan "/" jika tertulis di dokumen dan TIDAK menyertakan
    base_url (mis. /api/v1/...). Jika dokumen TIDAK mencantumkan path sama sekali,
    isi path dengan string kosong "" , lalu set "needs_review": true dan isi
    review_reason yang menjelaskan bahwa path tidak ada. JANGAN mengisi path
    dengan nilai karangan.
- Headers: tulis sebagai objek JSON "kunci": "nilai" (satu pasangan per baris).
- Query Params: tulis sebagai objek JSON "kunci": "nilai".
    Jika sebuah parameter muncul BERULANG dalam satu tabel (mis. tag=a&tag=b),
    tulis nilainya sebagai ARRAY: {"tag": ["a", "b"]}. Jika hanya satu, cukup string.
- Body (JSON): tulis sebagai objek JSON valid apa adanya.
- Expected Status Code: hanya berisi bilangan bulat kode HTTP.
- Expected Schema: SALIN TERLENGKAPNYA VERBATIM (termasuk "field (type)") ke expected.schema_narration. JANGAN ubah kata-kata atau dikonversi menjadi JSON.
- Simbol "(tidak ada)", "Tidak ada", "-", atau kosong:
    - Untuk field nullable string (summary, regex, schema_narration,
      review_reason), gunakan null.
    - Untuk request.body yang kosong, gunakan null (bila terisi, body tetap
      boleh berupa objek, array, atau primitif).
    - Untuk field bertipe daftar (request.headers, request.query,
      expected.jsonpath, expected.contains), gunakan {} atau [] kosong.
- Jika ada informasi yang tidak jelas, tidak lengkap, atau berpotensi salah:
    WAJIB set "needs_review": true DAN WAJIB isi "review_reason" menjelaskan
    masalahnya. review_reason tidak pernah boleh kosong saat needs_review bernilai true.
""".strip()

_OUTPUT_INSTRUCTION = """
Keluarkan SEMUA data di atas dalam SATU objek JSON valid dan TIDAK ADA teks lain di luar objek JSON. Gunakan struktur ini:
{
  "id": string,
  "title": string,
  "summary": string atau null,
  "request": {
    "method": "GET | POST | PUT | PATCH | DELETE",
    "path": string,
    "headers": {"kunci": "nilai"},
    "query": {"kunci": "nilai" atau ["nilai"]},
    "body": object, array, primitif, atau null
  },
  "expected": {
    "status": integer atau null,
    "schema_narration": string atau null,
    "jsonpath": ["..."],
    "regex": string atau null,
    "contains": ["..."]
  },
  "needs_review": boolean,
  "review_reason": string atau null
}
""".strip()


_SYSTEM_ANALYST_PROMPT = (
    "Kamu adalah analis ambiguitas test case API. Tugasmu hanya menandai "
    "bagian yang ambigu, tidak lengkap, atau berpotensi salah. Kamu TIDAK "
    "PERNAH menentukan lulus/gagal dan TIDAK PERNAH mengarang nilai."
)


def build_case_prompt(table_text: str) -> list[dict]:
    """Build the messages list that translates one table into a TestCase JSON.

    Args:
        table_text: the raw table content (label + fields) for one test case.

    Returns:
        A chat message list (system + task + few-shot + conventions) ending
        with the table to translate. The LLM's answer is parsed elsewhere.
    """
    task = (
        "Terjemahkan SATU tabel test case berikut menjadi JSON sesuai skema. "
        "Ikuti contoh, konvensi, dan struktur output di bawah ini dengan presisi."
    )

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"{task}\n\n{_FEW_SHOT}\n\n{_CONVENTIONS}\n\n{_OUTPUT_INSTRUCTION}\n\nTabel:\n{table_text}",
        },
    ]
    return messages


def build_analyze_prompt(case: dict, verdict_note: str = "") -> list[dict]:
    """Build a prompt for ambiguity analysis of a single case."""
    instruction = (
        "Analyze the following API test case. Identify ambiguous, incomplete, "
        "or potentially incorrect parts. Return ONLY JSON in the form "
        '{"needs_review": bool, "review_reason": string|null}, no other text. '
        "Do NOT decide pass/fail."
    )
    content = f"{instruction}\n\nContext: {verdict_note or '(none)'}\n\n{json.dumps(case, ensure_ascii=False)}"
    return [
        {"role": "system", "content": _SYSTEM_ANALYST_PROMPT},
        {"role": "user", "content": content},
    ]


_SYSTEM_EXPLAIN_PROMPT = (
    "You are an API test failure analyst. Explain why an API test case failed "
    "in clear, concise Indonesian. Your explanation must focus only on the "
    "mismatch between the expected behavior and the actual response. Never "
    "invent facts. Do not say the server responded correctly or appropriately "
    "when the test failed. If the status code is wrong, explicitly state the "
    "expected status code and the actual status code received."
)


_SYSTEM_OPENAPI_CONVERT_PROMPT = (
    "You are an API test suite generator. Convert an OpenAPI specification "
    "into a list of test cases that strictly follow the provided template. "
    "Use clear, concise Indonesian language for titles and descriptions. "
    "Never invent facts not present in the OpenAPI spec."
)


_OPENAPI_TEMPLATE_INSTRUCTION = """
Convert the OpenAPI specification below into a JSON array of test cases.
Each test case must use EXACTLY these keys and follow the standard template format:

{
  "id": "TC-001",
  "judul": "Judul singkat skenario pengujian",
  "deskripsi": "Penjelasan singkat tujuan test case",
  "method": "GET",
  "path": "/api/v1/resource",
  "headers": "Content-Type: application/json",
  "query_params": "(tidak ada)",
  "body": "(tidak ada)",
  "expected_status_code": "200",
  "expected_schema": "Response harus memuat field: id (number), name (string)",
  "jsonpath_checks": "$.id",
  "regex": "(tidak ada)",
  "contains": "(tidak ada)"
}

Rules:
- Generate one test case per endpoint/method combination.
- ID must follow the pattern TC-001, TC-002, TC-003, etc.
- For fields that are empty or not applicable, use the exact string "(tidak ada)".
- Method must be one of: GET, POST, PUT, PATCH, DELETE.
- Path must start with "/" and must NOT include the base URL.
- Headers should include "Content-Type: application/json" only when body is present.
- For request body, use the example from the spec if available. If no example exists, use "(tidak ada)".
- Expected status code should be a 2xx code from the spec responses, or 200 as default.
- Expected schema should describe the top-level response fields with types, e.g. "id (number), name (string)".
- JSONPath checks should list simple paths to verify important fields, e.g. "$.id" or "$.status".
- Regex and contains are optional; use "(tidak ada)" when not needed.

Return ONLY a JSON object in this exact form, no other text:
{
  "cases": [ ... ],
  "failed": []
}

If any endpoint cannot be converted, include a short reason in the "failed" array.
""".strip()


def build_openapi_convert_prompt(openapi_json: str) -> list[dict]:
    """Build a prompt that converts an OpenAPI JSON spec into test cases."""
    return [
        {"role": "system", "content": _SYSTEM_OPENAPI_CONVERT_PROMPT},
        {
            "role": "user",
            "content": f"{_OPENAPI_TEMPLATE_INSTRUCTION}\n\nOpenAPI spec:\n{openapi_json}",
        },
    ]


def build_explain_prompt(
    case: dict,
    http_result: dict | None,
    assertion_details: list[dict],
) -> list[dict]:
    """Build a prompt that asks the LLM to explain why a test failed."""
    instruction = (
        "The following API test case FAILED. Explain in 2-4 sentences why it "
        "failed, using only the request, expected result, actual response, and "
        "assertion details below. Rules: "
        "1) Focus on the exact mismatch. "
        "2) If the status code is wrong, state the expected code and the actual code. "
        "3) Do not say the server responded correctly or that the behavior is appropriate. "
        "4) Do not add reassuring or contradictory language. "
        'Return ONLY JSON in the form {"explanation": string}, no other text.'
    )
    payload = {
        "test_case": case,
        "actual_response": http_result,
        "assertion_details": assertion_details,
    }
    content = f"{instruction}\n\n{json.dumps(payload, ensure_ascii=False)}"
    return [
        {"role": "system", "content": _SYSTEM_EXPLAIN_PROMPT},
        {"role": "user", "content": content},
    ]
