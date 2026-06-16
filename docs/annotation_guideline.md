# Vietnamese Clickbait Annotation Guideline v3 (Research-Grade)

This document serves as the absolute source of truth for labeling Vietnamese clickbait headlines. All LLM prompts must adhere to these operational definitions.

## 1. Core Rubric

An article is labeled as **CLICKBAIT (1)** if its `rubric_total` is $\ge 4$, where `rubric_total` is the rounded average of the ensemble models' total rubric scores: `rubric_total = round((sum_A + sum_B) / 2)`. Each model evaluates 4 criteria (C1–C4), scoring each on a 0–2 scale, for a maximum of 8 points per model. Otherwise, the article is **NOT CLICKBAIT (0)**.

### Criterion 1: Sensationalism (Phóng đại cảm xúc)
- **Definition:** Use of extreme adjectives, emotional triggers, or sensationalist language to manipulate the reader's emotions, even when the content does not justify such intensity.
- **Indicators:** 
    - Hyperbolic words: "Sốc", "Kinh hoàng", "Không thể tin nổi", "Đỉnh cao", "Thảm họa", "Vỡ òa", "Ám ảnh".
    - Emotional punctuation: Excessive use of "!!!" or "???".
- **Contrast Example:**
    - ✅ CLICKBAIT: "Kinh hoàng: Căn nhà bị san phẳng trong 1 giây, hình ảnh gây ám ảnh!" (Over-sensationalized).
    - ❌ NOT CLICKBAIT: "Vụ hỏa hoạn lớn tại quận 1 khiến 1 căn nhà bị thiêu rụi." (Objective description).

### Criterion 2: Information Gap (Khoảng trống thông tin)
- **Definition:** The headline deliberately withholds key information (subject, result, action) to create a curiosity gap, forcing the reader to click to find the answer.
- **Indicators:** 
    - Use of non-specific pronouns: "người này", "điều đó", "bí mật này", "sự thật này".
    - Ellipses or cliffhangers: "tiết lộ lý do...", "bí mật đằng sau điều này...", "người đàn ông đứng sau...".
- **Contrast Example:**
    - ✅ CLICKBAIT: "Nam ca sĩ nổi tiếng vừa tiết lộ sự thật về đời tư khiến fan ngỡ ngàng." (Who is the singer? What is the truth?)
    - ❌ NOT CLICKBAIT: "Sơn Tùng M-TP tiết lộ chi tiết về album mới trong buổi phỏng vấn." (Specific subject and topic).

### Criterion 3: Syntactic Framing (Định khung cú pháp)
- **Definition:** Using patterns of direct commands, imperative phrasing, or highly suggestive/provocative rhetorical questions to steer reader behavior.
- **Indicators:** 
    - Direct commands: "Xem ngay kẻo lỡ!", "Chớ dại làm điều này", "Hãy đọc trước khi bị xóa".
    - Rhetorical/provocative questions: "Liệu bạn có dám...?", "Ai mới là kẻ chịu trách nhiệm?".
- **Contrast Example:**
    - ✅ CLICKBAIT: "Hãy xem ngay video này trước khi bị gỡ bỏ vì quá nhạy cảm!" (False urgency).
    - ❌ NOT CLICKBAIT: "Video chi tiết về hướng dẫn cài đặt phần mềm (Cập nhật 2026)." (Useful information).

### Criterion 4: Incongruence (Tính bất tương đồng)
- **Definition:** The headline creates an expectation or makes a claim that is not supported, is contradicted, or is significantly exaggerated compared to the actual content (sapo/body text).
- **Indicators:** 
    - Headlines that promise a "revelation" that turns out to be common knowledge.
    - Claims of "huge drops/increases" when the actual number is negligible.
- **Contrast Example:**
    - ✅ CLICKBAIT: "Giá vàng hôm nay giảm sâu, cơ hội vàng để mua vào" $\rightarrow$ (Content shows only a 0.1% drop).
    - ❌ NOT CLICKBAIT: "Giá vàng hôm nay biến động nhẹ, giảm 10.000đ/chỉ." (Accurate).

## 2. Annotation Process for LLMs

To avoid "Lazy Labeling", LLMs must follow this sequence:
1. **Evidence Extraction:** Identify specific words/phrases in the headline that trigger any of the 4 criteria.
2. **Content Verification:** Compare the extracted evidence with the sapo/body.
3. **Rubric Mapping:** Map the evidence to a specific criterion.
4. **Final Decision:** If the ensemble `rubric_total` $\ge 4 \rightarrow$ Label 1. Else $\rightarrow$ Label 0.

## 3. Hard Constraints
- **No "Attractive" Bias:** A headline can be "attractive" or "well-written" without being clickbait. If it is attractive but provides enough core information, it is Label 0.
- **Evidence Requirement:** If Label 1 is chosen, the `reason` field MUST quote the specific words from the headline.
