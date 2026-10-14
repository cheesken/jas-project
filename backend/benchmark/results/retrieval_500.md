# Retrieval benchmark (500 documents)

Run 2026-10-13T23:27:09+00:00. 50 queries (14 keyword, 14 phrase, 22 question), 500 documents (150 note, 100 email, 100 pdf, 150 history), 500 chunks. Embedding model `all-MiniLM-L6-v2`, NER model `en_core_web_sm`. Indexing took 19.0 s.

| System | NDCG@10 | P@5 | MRR | Answer MRR |
| --- | --- | --- | --- | --- |
| bm25 | 0.780 | 0.636 | 0.884 | 0.671 |
| semantic | 0.853 | 0.656 | 0.972 | 0.780 |
| semantic+kg | 0.856 | 0.660 | 0.972 | 0.783 |

Targets (workbook 7.2): NDCG@10 >= 0.65, P@5 >= 0.6, MRR >= 0.65. P@5 counts grade 1 and 2 as relevant; each query has 4 relevant documents, so the best possible P@5 is 0.80. Answer MRR is the reciprocal rank of the document that answers the query (grade 2).

## NDCG@10 by query kind

| System | keyword | phrase | question |
| --- | --- | --- | --- |
| bm25 | 0.898 | 0.867 | 0.649 |
| semantic | 0.851 | 0.880 | 0.837 |
| semantic+kg | 0.840 | 0.903 | 0.837 |

## Per query (NDCG@10)

| Query | Kind | bm25 | semantic | semantic+kg |
| --- | --- | --- | --- | --- |
| q01: Which restaurant did Tara recommend? | question | 0.415 | 0.658 | 0.658 |
| q02: passport appointment | keyword | 1.000 | 0.781 | 0.781 |
| q03: When is my teeth cleaning? | question | 0.283 | 0.975 | 0.975 |
| q04: apartment lease end date | phrase | 0.686 | 0.906 | 0.906 |
| q05: wifi password | keyword | 1.000 | 1.000 | 1.000 |
| q06: What time does my flight to Japan leave? | question | 0.254 | 0.744 | 0.744 |
| q07: gym membership cancellation | phrase | 0.906 | 1.000 | 1.000 |
| q08: What did I plan to gift my mother for her birthday? | question | 0.862 | 0.744 | 0.744 |
| q09: workbook deadline | keyword | 0.781 | 0.188 | 0.188 |
| q10: When does my car insurance renew? | question | 0.283 | 0.890 | 0.890 |
| q11: dal makhani recipe | phrase | 0.838 | 1.000 | 0.838 |
| q12: How much base pay did they offer me? | question | 0.845 | 0.658 | 0.658 |
| q13: AppleCare coverage | keyword | 0.947 | 0.990 | 0.990 |
| q14: Which novel did Aditi suggest I read? | question | 0.415 | 0.906 | 0.906 |
| q15: Dr Patel appointment time | phrase | 0.750 | 0.781 | 0.781 |
| q16: Is my streaming subscription getting more expensive? | question | 0.000 | 0.829 | 0.829 |
| q17: PG&E bill amount | keyword | 0.781 | 1.000 | 0.838 |
| q18: Big Basin hike plan | phrase | 0.781 | 0.838 | 0.838 |
| q19: When is Pooja getting married? | question | 0.906 | 1.000 | 1.000 |
| q20: OPT EAD dates | keyword | 0.862 | 0.906 | 0.906 |
| q21: campus parking permit number | phrase | 0.838 | 1.000 | 1.000 |
| q22: By when do I need to send back the headphones? | question | 0.000 | 0.799 | 0.799 |
| q23: Who is responsible for the file watcher? | question | 0.767 | 0.796 | 0.796 |
| q24: W-2 wages | keyword | 0.838 | 0.990 | 0.990 |
| q25: How often should I water the monstera? | question | 0.975 | 0.906 | 0.906 |
| q26: Chase credit card payment due | phrase | 1.000 | 0.990 | 0.990 |
| q27: Where are my seats for the Arijit Singh concert? | question | 0.781 | 0.838 | 0.838 |
| q28: oil change Civic | keyword | 0.990 | 0.990 | 0.990 |
| q29: Trader Joe's shopping list | phrase | 1.000 | 0.781 | 1.000 |
| q30: When is the library book due back? | question | 0.940 | 0.352 | 0.352 |
| q31: advisor feedback on literature review | phrase | 0.755 | 0.686 | 0.686 |
| q32: Mint Mobile renewal | keyword | 0.722 | 1.000 | 1.000 |
| q33: Did I pay the rent this month? | question | 0.722 | 0.750 | 0.750 |
| q34: Tdap booster date | keyword | 0.658 | 0.796 | 0.796 |
| q35: hackathon registration deadline | phrase | 1.000 | 1.000 | 1.000 |
| q36: What time do I need to pick up Arjun? | question | 0.894 | 1.000 | 1.000 |
| q37: What coffee does Siddharth like? | question | 1.000 | 0.813 | 0.813 |
| q38: checking routing number | keyword | 1.000 | 0.658 | 0.658 |
| q39: How much tea powder goes into masala chai? | question | 1.000 | 0.984 | 0.984 |
| q40: CHI paper submission deadline | phrase | 0.750 | 0.744 | 1.000 |
| q41: Where did I leave my umbrella? | question | 0.750 | 1.000 | 1.000 |
| q42: MALM bed frame | keyword | 1.000 | 1.000 | 1.000 |
| q43: Dune showtimes AMC | phrase | 1.000 | 1.000 | 1.000 |
| q44: Which design software company did I apply to? | question | 0.509 | 0.767 | 0.767 |
| q45: Santa Clara apartments | keyword | 1.000 | 0.781 | 0.781 |
| q46: When is my driving test? | question | 0.678 | 1.000 | 1.000 |
| q47: food bank donation receipt | phrase | 1.000 | 0.817 | 0.817 |
| q48: Who fixed the kitchen sink? | question | 1.000 | 1.000 | 1.000 |
| q49: Karpathy podcast | keyword | 1.000 | 0.838 | 0.838 |
| q50: yoga class booking | phrase | 0.838 | 0.781 | 0.781 |
