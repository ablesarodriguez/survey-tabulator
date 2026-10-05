# Data

`sample_survey.sav` is a **synthetic** survey: 6,000 interviews in four waves about the services of a
city that does not exist. Every answer is drawn at random by `tools/make_sample_data.py`; it contains
no real respondents and no data from any real study. It is here so that the application can be tried
straight after cloning, and it is the file behind every screenshot in the main README.

`sample_library.sav` is a second synthetic file, deliberately unlike the first: 1,500 answers from the
users of an invented library network, in a single wave, without weights, and with other special codes
(-1111 "Prefers not to say", 5555 "Not applicable"). Opening one after the other shows that the
application takes everything from the file and nothing from a fixed questionnaire.

Regenerate them, or write a larger one for benchmarking, with:

```bash
python tools/make_sample_data.py
python tools/make_sample_data.py --library
python tools/make_sample_data.py --rows 2000000 --extra-variables 72 --out big.sav
```

Any other `.sav` file is ignored by git, so real survey data dropped in this folder is never committed.

## What the file contains

| Variables | Kind | What it exercises |
| --- | --- | --- |
| `YEAR` | wave, 2022 to 2025 | one column per year, year filter |
| `WEIGHT`, `WEIGHT_ONLINE` | weighting coefficients | weighted counts and bases |
| `SEX`, `AGE_GROUP`, `DISTRICT`, `EDUCATION`, `EMPLOYMENT`, `HOUSING`… | single choice | plain frequency tables |
| `SAT_*`, `TRUST_COUNCIL`, `RECOMMEND` | 0-10 and 1-10 scales | mean and standard deviation |
| `CAR_FUEL` | only asked to households with a car (code 7777 otherwise) | filtered question, reduced base |
| `DEVICE`, `APP_USE`, `SAT_WEBSITE` | only asked online (code 4444 otherwise) | online weight and online base |
| all of the above | codes 8888 "Don't know" and 9999 "No answer" | special values |
