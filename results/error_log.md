# Nhật ký lỗi và xử lý

| Bước | Hiện tượng quan sát | Xử lý và kết quả |
|---|---|---|
| Chọn corpus | Bản PDF 160 trang ban đầu cho văn bản rỗng ở cả 160 trang khi đọc bằng `pypdf`. | Dùng bản Springer có lớp văn bản. Kiểm tra lại và trích xuất được cả 67 trang trong manifest. |
| Trích xuất PDF | `pypdf` cảnh báo về mã hóa phông CFF Type1. Một số từ bị ngắt và một số ký hiệu công thức có thể bị mất. | Chuẩn hóa Unicode và khoảng trắng, giữ số trang để đối chiếu. Kiểm tra 20 đoạn trích chuẩn xuất hiện ở trang đã khai báo sau chuẩn hóa. |
| Thử OpenAI Embeddings | Phiên chạy đầu báo lỗi phân giải tên miền `getaddrinfo failed`. | Thử lại với quyền truy cập mạng. API trả hai vector 1.536 chiều, sau đó chạy thành công benchmark chính và lượt so sánh Anh–Việt. |
| Kiểm tra PostgreSQL | Phiên kiểm tra ban đầu không kết nối được database local. | Kiểm tra lại với quyền truy cập dịch vụ local, nhận `Setup OK` với PostgreSQL 16.16 và pgvector 0.8.7. |
| Đối chiếu kết quả test | `q19` có bằng chứng tương đương ở trang PDF 56 mà gold ban đầu chưa liệt kê. | Ghi nhận bằng chứng trong bảng grounding và báo cáo. Các chỉ số tự động tiếp tục phản ánh lần chạy với bộ gold ban đầu. |
