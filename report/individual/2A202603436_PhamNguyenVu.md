# Báo cáo cá nhân — Day 06 Data Ingestion Engineering

**Phạm Nguyên Vũ · MSSV 2A202603436 · Lớp L3A**

## Dữ liệu và pipeline

Corpus gồm 67 trang có nội dung từ hai chương do Wil M. P. van der Aalst viết trong *Process Mining Handbook* (Springer Cham, 2022). Bản PDF dùng trong bài có 503 trang vật lý. Chương tổng quan dùng trang PDF 12–41 (trang in 3–32), còn chương *Foundations of Process Discovery* dùng trang PDF 45–81 (trang in 37–73). Danh sách giữ các trang còn nội dung chính và loại bìa, mục lục, các chương khác và trang chỉ có tài liệu tham khảo hoặc giấy phép. Bản sách phát hành theo CC BY 4.0, có ngoại lệ theo ghi chú quyền riêng của từng tài liệu được trích dẫn. [Nguồn Springer](https://doi.org/10.1007/978-3-031-08848-3) · [Giấy phép](https://creativecommons.org/licenses/by/4.0/) · [Manifest](../../data/manifest.json)

`pypdf` 6.21.4 đọc từng trang. Pipeline chuẩn hóa Unicode theo NFKC, nối dòng và giữ ranh giới đoạn bằng dòng trống nếu PDF cung cấp. Bản PDF ảnh 160 trang kiểm tra ban đầu cho văn bản rỗng. Bản Springer trích xuất được cả 67 trang đã chọn. Một số từ vẫn có dấu gạch nối do ngắt dòng, ký hiệu trong công thức có thể bị mất và tiêu đề đầu trang có thể xuất hiện trong chunk. Hàm đọc ghi log cho trang rỗng hoặc lỗi, và nạp corpus dừng nếu thiếu trang đã khai báo.

Mỗi chunk lưu `document_id`, `source` là DOI dạng URL, `page` là thứ tự vật lý từ 1, `printed_page` là số in trên sách và `chapter` là nhãn lấy theo ranh giới chương trong manifest. `chapter` cho phép giới hạn kết quả trong chương người dùng đang đọc. `page` và `printed_page` giúp người đọc mở đúng trang khi số trang PDF lệch với số in trên sách.

Pipeline dùng OpenAI `text-embedding-3-small` với 1.536 chiều cho cả đoạn văn lẫn câu hỏi. PostgreSQL 16.16 và pgvector 0.8.7 lưu vector, truy xuất chính xác theo cosine và trả top 3. Kiểm tra nạp lại A bằng vector đã lưu cho thấy số bản ghi giữ ở 433, với 433 ID duy nhất. B có 454 bản ghi và 454 ID duy nhất.

Từ thư mục gốc, sau khi khởi động PostgreSQL và cấu hình `OPENAI_API_KEY`, chạy:

```powershell
.\starter\.venv\Scripts\python.exe -m starter.src.run
```

## Cấu hình và benchmark

| Cấu hình | Cách chia chunk | Truy xuất |
|---|---|---|
| A | Cửa sổ 500 ký tự, chồng lấn 50 ký tự | Cosine trên toàn corpus |
| B | Gom đoạn đến 500 ký tự, ưu tiên tách ở cuối câu rồi đến ranh giới từ | Cosine trên toàn corpus |
| C | Dùng chung chunk và vector với B | Áp dụng bộ lọc `chapter` cho câu có phạm vi chương |

Bộ câu hỏi tiếng Anh gồm 15 dev và 5 test, chia trước lần truy xuất. Có hai câu có filter ở dev và một câu ở test. Bộ lọc đến từ phạm vi chương nêu trong câu hỏi. Kiểm tra chuỗi đã xác nhận 20/20 đoạn trích xuất hiện trên đúng trang PDF sau chuẩn hóa. Các câu dev và test dùng các trang bằng chứng khác nhau, song cùng lấy từ hai chương và có thể chia sẻ thuật ngữ hoặc chủ đề. [Bộ câu hỏi](../../benchmark/questions.json)

Tiêu chí đã áp dụng trước khi truy xuất test là tối đa hóa Evidence Hit@3 trên dev, dùng Hit@1 để phân xử, rồi ưu tiên A, B, C nếu vẫn hòa. C được chọn nhờ Hit@1 cao hơn B khi cả hai cùng đạt 8/15 Evidence Hit@3. [Quyết định trên dev](../../results/selection.json)

### Thiết kế so sánh câu hỏi tiếng Anh và tiếng Việt

Mỗi câu tiếng Việt tương ứng một câu tiếng Anh theo ID `q01`–`q20`. Hai bản dùng chung đáp án, bằng chứng chuẩn, cách chia 15 dev và 5 test, cùng phạm vi lọc. Cả hai được chạy lại với `text-embedding-3-small` trên cùng kho vector của tài liệu tiếng Anh. Bản dịch được thêm sau benchmark gốc, nên phép so sánh dùng 20 cặp trên cùng 20 nội dung câu hỏi. [Câu hỏi tiếng Việt](../../benchmark/questions_vi.json)

## Kết quả

| Cấu hình | Chunk | Ký tự trung bình/chunk | Dev Hit@1 | Dev Evidence Hit@3 | Test Hit@1 | Test Evidence Hit@3 |
|---|---:|---:|---:|---:|---:|---:|
| A | 433 | 466,74 | 5/15 | 7/15 | 1/5 | 3/5 |
| B | 454 | 403,99 | 4/15 | 8/15 | 1/5 | 1/5 |
| C | 454, dùng chung B | 403,99 | 5/15 | 8/15 | 1/5 | 1/5 |

| Phần đo | Token đầu vào | Thời gian tạo và lưu vector | Chi phí API ước tính (USD) |
|---|---:|---:|---:|
| Chunk A | 54.229 | 10,116 giây | 0,001085 |
| Chunk B | 48.906 | 7,321 giây | 0,000978 |
| Chunk C, dùng chung B | 0 thêm | Dùng chung thời gian của B | 0 thêm |
| Câu hỏi dev và test, dùng chung cho A/B/C | 341 | Chưa đo riêng | 0,000007 |
| Tổng | 103.476 | 21,244 giây ingest, gồm đọc, chia và lưu | 0,002070 |

Chi phí tính theo 0,02 USD trên một triệu token đầu vào. Thời gian ghi nhận từ một lần chạy vào ngày 13/11/2026. [Giá OpenAI](https://developers.openai.com/api/docs/models/text-embedding-3-small) · [Bảng tổng hợp](../../results/summary.json) · [Nhật ký thí nghiệm](../../artifacts/experiment_log.csv)

| Cấu hình | Coherence trung bình /2 (n=10) | Metadata đủ và đúng (test) | Tuân thủ filter (dev / test) | Grounding test, số câu ở mức 0/1/2 | Grounding trung bình /2 |
|---|---:|---:|---:|---:|---:|
| A | 1,0 | 15/15 | 2/2 · 1/1 | 2 / 0 / 3 | 1,2 |
| B | 1,6 | 15/15 | 1/2 · 1/1 | 1 / 2 / 2 | 1,2 |
| C | 1,6 | 15/15 | 2/2 · 1/1 | 1 / 2 / 2 | 1,2 |

Mẫu coherence lấy chunk chứa vị trí ký tự đầu tiên trên 10 trang đầu trong manifest (PDF 12–21), dùng cùng vị trí cho A, B và C. C dùng cùng chunk và cùng điểm với B. Grounding đọc cả ba đoạn của mỗi lượt test và chấm 0 khi thiếu bằng chứng trả lời, 1 khi chỉ đủ một phần và 2 khi đủ để trả lời và truy nguồn. Metadata được đối chiếu từng kết quả với DOI, số trang và chương trong manifest, nhãn trang của PDF và nội dung chunk tái tạo từ trang khai báo. Tỷ lệ tuân thủ filter tính trên số câu có yêu cầu phạm vi, kể cả khi A hoặc B tình cờ trả về đủ ba chunk đúng chương.

### Kết quả truy xuất theo ngôn ngữ câu hỏi

| Cấu hình | Dev Hit@1 Anh → Việt | Dev Evidence Hit@3 Anh → Việt | Test Hit@1 Anh → Việt | Test Evidence Hit@3 Anh → Việt |
|---|---:|---:|---:|---:|
| A | 5/15 → 3/15 | 7/15 → 5/15 | 1/5 → 1/5 | 3/5 → 1/5 |
| B | 4/15 → 1/15 | 8/15 → 2/15 | 1/5 → 1/5 | 1/5 → 1/5 |
| C | 5/15 → 1/15 | 8/15 → 2/15 | 1/5 → 1/5 | 1/5 → 1/5 |

Lượt so sánh dùng 341 token đầu vào cho 20 câu tiếng Anh và 904 token cho 20 câu tiếng Việt. [Bảng tổng hợp Anh–Việt](../../results/language_comparison/summary.json) · [Kết quả theo cặp](../../results/language_comparison/paired_outcomes.json)

## Phân tích và kết luận

- **A và B.** B tăng coherence từ 1,0 lên 1,6 trên mẫu và dùng ít hơn 5.323 token cho chunk. A đạt 3/5 Evidence Hit@3 trên test so với 1/5 của B. Ở `q17`, A hạng 3 (PDF 32, trang in 23) chứa ví dụ hai sự kiện bắt đầu và hai sự kiện hoàn thành có hai cách ghép. B hạng 1 cũng lấy PDF 32 nhưng chỉ giải thích vòng đời sự kiện. Phần ví dụ chồng lấn nằm ngoài đoạn trả về.
- **B và C.** Ở `q14` trên dev, filter đưa chunk trang PDF 52 từ hạng 2 lên hạng 1 sau khi loại chunk thuộc chương tổng quan. Ở `q18` trên test, cả B và C trả cùng ba trang PDF 48, 55, 58. Chúng đều đúng chương, nhưng thiếu bằng chứng ở PDF 54 (trang in 46) xác định arc-based filtering là bước cuối. Bộ lọc thu hẹp phạm vi, còn thứ hạng trong phạm vi đó phụ thuộc vào độ tương đồng của vector.
- **Giới hạn khi đối sánh evidence.** Ở `q19`, B và C trả đoạn ở PDF 56 (trang in 48) nêu đúng hai tỷ lệ. Gold ban đầu chỉ ghi PDF 57 (trang in 49), nên lượt đó được chấm grounding 2 và vẫn trượt Evidence Hit@3 tự động. Nên kiểm tra các vị trí bằng chứng tương đương trước lần đánh giá sau và ghi nhận bằng chứng đã phát hiện khi phân tích kết quả hiện tại.

Chọn C theo quy tắc trên dev. A có Evidence Hit@3 cao nhất trên tập test hiện tại. Tập test chỉ có năm câu, trong đó một câu yêu cầu lọc, nên một câu có thể làm tỷ lệ thay đổi 20 điểm phần trăm. Mẫu coherence chỉ lấy đầu trang và nằm trong chương tổng quan, nên kết quả chưa đại diện cho giữa trang hoặc chương thứ hai. Nếu mở rộng, có thể định trước các vị trí mẫu ở cả hai chương, cải thiện nhận diện ranh giới câu quanh chữ viết tắt như `Fig.`, rồi đo lại trên một tập test mới.

### Ảnh hưởng của ngôn ngữ câu hỏi

Trên dev, Evidence Hit@3 giảm 2 câu ở A và 6 câu ở mỗi cấu hình B và C khi chuyển sang tiếng Việt. Trên test, A mất hai hit ở `q16` và `q17`. Bản tiếng Anh tìm được bằng chứng ở trang PDF 28 và 32, còn top 3 của bản tiếng Việt đều nằm ngoài chương tổng quan chứa hai trang đó.

Với `q14` tiếng Việt, C trả cả ba chunk đúng chương `process_discovery`, nhưng trang PDF 52 chứa bằng chứng vắng mặt trong top 3. B và C có cùng điểm Hit@1 và Evidence Hit@3 cho các câu tiếng Việt ở cả hai tập. Trong lần chạy này, bộ lọc giúp giới hạn phạm vi, còn việc đưa đoạn có bằng chứng lên hạng cao vẫn phụ thuộc vào độ tương đồng giữa câu hỏi tiếng Việt và đoạn tiếng Anh. [Trace tiếng Anh](../../results/language_comparison/en_traces.json) · [Trace tiếng Việt](../../results/language_comparison/vi_traces.json)

Trên năm cặp test, cả ba cấu hình đều đạt 1/5 Evidence Hit@3 với câu tiếng Việt. Kết quả áp dụng cho 20 cặp câu đã dịch, corpus tiếng Anh và model đã dùng. Việc chọn C vẫn dựa trên dev tiếng Anh theo tiêu chí đã chốt.
