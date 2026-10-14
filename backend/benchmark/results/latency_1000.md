# Query latency (US-NF-02, 1000 documents)

Run 2026-10-13T23:35:21+00:00. 15 queries through `/query/stream` (the endpoint the desktop app uses), after a warm-up query. Ollama model `llama3:8b`; it answered 15 of 15.

**US-NF-02 (average time until results appear <= 30 s): PASS**, average 0.05 s.

| Measure | Average | Median | P95 | Max |
| --- | --- | --- | --- | --- |
| Results appear | 0.05 s | 0.04 s | 0.06 s | 0.08 s |
| Full LLM answer | 7.45 s | 6.08 s | 16.23 s | 23.64 s |

Indexing the corpus took 48.0 s (1249.1 documents per minute, single process).

## By query kind (average)

| Kind | Results appear | Full LLM answer |
| --- | --- | --- |
| keyword | 0.05 s | 6.42 s |
| phrase | 0.04 s | 11.06 s |
| question | 0.05 s | 4.86 s |

## Per query

| Query | Kind | Results | Answer |
| --- | --- | --- | --- |
| q02: passport appointment | keyword | 0.05 s | 6.36 s |
| q05: wifi password | keyword | 0.08 s | 3.38 s |
| q09: workbook deadline | keyword | 0.03 s | 7.68 s |
| q13: AppleCare coverage | keyword | 0.05 s | 8.58 s |
| q17: PG&E bill amount | keyword | 0.05 s | 6.08 s |
| q04: apartment lease end date | phrase | 0.05 s | 3.51 s |
| q07: gym membership cancellation | phrase | 0.04 s | 5.10 s |
| q11: dal makhani recipe | phrase | 0.04 s | 16.23 s |
| q15: Dr Patel appointment time | phrase | 0.04 s | 6.81 s |
| q18: Big Basin hike plan | phrase | 0.04 s | 23.64 s |
| q01: Which restaurant did Tara recommend? | question | 0.06 s | 3.49 s |
| q03: When is my teeth cleaning? | question | 0.04 s | 3.72 s |
| q06: What time does my flight to Japan leave? | question | 0.04 s | 4.86 s |
| q08: What did I plan to gift my mother for her birthday? | question | 0.05 s | 6.79 s |
| q10: When does my car insurance renew? | question | 0.04 s | 5.46 s |
