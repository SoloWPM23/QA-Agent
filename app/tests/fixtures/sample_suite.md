# Sample test suite in plain text form (used by text/chunk test).

Test Case TC-010: Ambil detail pengguna

ID: TC-010
Judul: Ambil detail pengguna berdasarkan ID
Deskripsi: Memastikan detail pengguna tertentu bisa diambil.
Method: GET
Path: /api/v1/users/1
Expected Status Code: 200
Contains: email

Test Case TC-011: Update pengguna

ID: TC-011
Judul: Perbarui email pengguna
Deskripsi: Memastikan data pengguna dapat diperbarui.
Method: PUT
Path: /api/v1/users/1
Expected Status Code: 200
Regex: ^\{.*\}$
