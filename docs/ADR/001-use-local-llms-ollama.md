# ADR 001: Lựa chọn Mô hình ngôn ngữ lớn chạy Local (Ollama) cho gán nhãn dữ liệu
## Context

Trong khuôn khổ đồ án DS108 UIT, mục tiêu của dự án là xây dựng bộ dữ liệu Clickbait tiếng Việt gồm 6,000 dòng. Quá trình gán nhãn đòi hỏi thực hiện chú giải song song trên 2 mô hình LLM độc lập để làm cơ sở tính toán chỉ số đồng thuận Inter-Annotator Agreement (IAA). 
Các lựa chọn ban đầu bao gồm:
1. Sử dụng API thương mại trả phí (GPT-4o, Gemini 1.5 Pro).
2. Tự huấn luyện/fine-tune mô hình nhỏ chạy offline.
3. Chạy local các mô hình open-source đã được lượng hóa thông qua Ollama.

Về mặt phần cứng, máy có cấu hình hạn chế: GPU RTX 3050 Ti (4GB VRAM) và RAM 8GB. Chi phí gọi API thương mại cho khối lượng dữ liệu lớn cũng vượt quá ngân sách nghiên cứu của đồ án học thuật.

## Decision

Chúng tôi quyết định **sử dụng hai mô hình ngôn ngữ lớn chạy cục bộ (local LLMs) thông qua Ollama**:
- **Model A**: `qwen2.5:3b-instruct-q4_K_M` (~2.5 GB VRAM)
- **Model B**: `gemma2:2b-instruct-q4_K_M` (~2.0 GB VRAM)

Quá trình chạy được thiết kế chạy **tuần tự (sequential pair processing)**: Chỉ load một mô hình vào VRAM tại một thời điểm, gán nhãn xong thì dọn dẹp bộ nhớ (unload keep_alive = 0) rồi mới load mô hình tiếp theo.

## Consequences

### Điểm tích cực (Consequences Good)
* **Chi phí bằng 0**: Hoàn toàn miễn phí, không phát sinh chi phí gọi API bên ngoài.
* **An toàn dữ liệu & Offline**: Dữ liệu tin tức crawl về được gán nhãn offline, không bị chia sẻ cho bên thứ ba.
* **Kiểm soát phần cứng**: Tận dụng tối đa card RTX 3050 Ti 4GB VRAM bằng lượng hóa Q4_K_M mà không gây tràn bộ nhớ (Out-Of-Memory).
* **Tái lập dễ dàng**: Ollama hỗ trợ cài đặt chạy mô hình bằng dòng lệnh đơn giản, Docker Compose dễ dàng tích hợp.

### Điểm hạn chế (Consequences Bad)
* **Tốc độ xử lý**: Do cấu hình GPU yếu và chạy tuần tự, tốc độ gán nhãn sẽ chậm hơn so với gọi API đám mây song song.
* **Độ lệch nhãn (Skew)**: Qwen 2.5 3B có thiên hướng gán nhãn clickbait rất khắt khe (conservative), trong khi Gemma 2 2B lại rất thoáng (aggressive), dẫn tới tỷ lệ bất đồng thuận khá cao (~66.13%) buộc phải có bước trọng tài của con người (Human-in-the-loop).
