# Mock API untuk End-to-End Test

Folder ini berisi mock REST API dan test suite yang cocok untuk menjalankan pipeline AI QA Agent dari ujung ke ujung.

## Isi

- `api.py` — FastAPI mock API dengan 10 endpoint.
- `generate_test_suite.py` — script untuk membuat `test_suite.docx` sesuai template standar.
- `test_suite.docx` — dokumen test suite siap upload.

## Endpoint

| Method | Path | Keterangan |
|---|---|---|
| GET | `/health` | Health check |
| GET | `/api/v1/users` | Daftar pengguna |
| GET | `/api/v1/users/{id}` | Detail pengguna (bug: id=1 dikembalikan sebagai string) |
| POST | `/api/v1/users` | Buat pengguna baru |
| PUT | `/api/v1/users/{id}` | Update pengguna |
| DELETE | `/api/v1/users/{id}` | Hapus pengguna |
| GET | `/api/v1/books` | Daftar buku |
| GET | `/api/v1/books/{id}` | Detail buku (bug: id=99 mengembalikan 200 bukan 404) |
| POST | `/api/v1/login` | Login |
| GET | `/api/v1/me` | Data user saat ini (perlu Bearer token) |

## Menjalankan Mock API

```bash
venv\Scripts\python.exe -m uvicorn mock.api:app --host 127.0.0.1 --port 9000
```

API akan tersedia di `http://127.0.0.1:9000`.

## Reset State

Mock API menyimpan data di memory. Untuk mengembalikan state ke kondisi awal tanpa restart server:

```bash
curl -X POST http://127.0.0.1:9000/reset
```

Endpoint ini berguna saat menjalankan test suite berulang kali.

## Menjalankan Test Suite dengan CLI

Pastikan mock API berjalan, lalu:

```bash
venv\Scripts\python.exe -m app.cli --suite mock/test_suite.docx --base-url http://127.0.0.1:9000 --auth-type none --output reports/mock
```

## Hasil yang Diharapkan

- 8 case PASS
- 2 case FAIL (TC-003 karena id string, TC-008 karena status 200 bukan 404)
- Exit code: 1
