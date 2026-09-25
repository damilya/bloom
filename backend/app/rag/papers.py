"""Curated open-access research corpus (all CC-licensed, via PubMed Central).

Selection criteria: (1) directly answers questions the three personas get about women / PCOS /
cycle / fasted training / protein; (2) highest available evidence tier (international guideline,
position stand, meta-analysis) with a few primary studies for nuance; (3) open access so the
full text can be indexed and quoted legally.
"""

PAPERS = [
    {"pmcid": "PMC10505534", "ref": "Teede et al., 2023", "year": 2023, "level": "international guideline",
     "title": "Recommendations from the 2023 International Evidence-based Guideline for the Assessment and Management of PCOS",
     "doi": "10.1210/clinem/dgad463", "topics": ["pcos", "lifestyle", "diagnosis", "exercise", "diet"]},
    {"pmcid": "PMC10210857", "ref": "Sims et al., 2023 (ISSN)", "year": 2023, "level": "position stand",
     "title": "ISSN Position Stand: Nutritional Concerns of the Female Athlete",
     "doi": "10.1080/15502783.2023.2204066", "topics": ["female athlete", "nutrition", "cycle", "fasting", "energy availability"]},
    {"pmcid": "PMC7719906", "ref": "Bull et al., 2020 (WHO)", "year": 2020, "level": "international guideline",
     "title": "World Health Organization 2020 guidelines on physical activity and sedentary behaviour",
     "doi": "10.1136/bjsports-2020-102955", "topics": ["physical activity", "guidelines"]},
    {"pmcid": "PMC5477153", "ref": "Jäger et al., 2017 (ISSN)", "year": 2017, "level": "position stand",
     "title": "ISSN Position Stand: Protein and Exercise",
     "doi": "10.1186/s12970-017-0177-8", "topics": ["protein", "nutrition", "muscle"]},
    {"pmcid": "PMC7358428", "ref": "Patten et al., 2020", "year": 2020, "level": "systematic review & meta-analysis",
     "title": "Exercise Interventions in Polycystic Ovary Syndrome: A Systematic Review and Meta-Analysis",
     "doi": "10.3389/fphys.2020.00606", "topics": ["pcos", "exercise", "insulin"]},
    {"pmcid": "PMC8835550", "ref": "dos Santos et al., 2022", "year": 2022, "level": "systematic review & meta-analysis",
     "title": "The Effect of Exercise on Cardiometabolic Risk Factors in Women with PCOS",
     "doi": "10.3390/ijerph19031386", "topics": ["pcos", "exercise", "cardiometabolic"]},
    {"pmcid": "PMC11099481", "ref": "Fitz et al., 2024", "year": 2024, "level": "systematic review & meta-analysis",
     "title": "Inositol for PCOS: A Systematic Review and Meta-analysis to Inform the 2023 International Guideline",
     "doi": "10.1210/clinem/dgad762", "topics": ["pcos", "supplements", "inositol"]},
    {"pmcid": "PMC9513052", "ref": "Zhang et al., 2022", "year": 2022, "level": "systematic review & meta-analysis",
     "title": "Sleep disturbances, sleep quality, and cardiovascular risk factors in women with PCOS",
     "doi": "10.3389/fendo.2022.971604", "topics": ["pcos", "sleep"]},
    {"pmcid": "PMC7497427", "ref": "McNulty et al., 2020", "year": 2020, "level": "systematic review & meta-analysis",
     "title": "The Effects of Menstrual Cycle Phase on Exercise Performance in Eumenorrheic Women",
     "doi": "10.1007/s40279-020-01319-3", "topics": ["cycle", "performance"]},
    {"pmcid": "PMC10076834", "ref": "Colenso-Semple et al., 2023", "year": 2023, "level": "narrative review",
     "title": ("Current evidence shows no influence of women's menstrual cycle phase on acute strength performance "
               "or adaptations to resistance exercise training"),
     "doi": "10.3389/fspor.2023.1054542", "topics": ["cycle", "strength", "resistance training"]},
    {"pmcid": "PMC11870050", "ref": "Colenso-Semple et al., 2025", "year": 2025, "level": "controlled study",
     "title": "Menstrual cycle phase does not influence muscle protein synthesis or whole-body myofibrillar proteolysis",
     "doi": "10.1113/jp287342", "topics": ["cycle", "protein", "muscle"]},
    {"pmcid": "PMC8053180", "ref": "Elliott-Sale et al., 2021", "year": 2021, "level": "methodological guide",
     "title": "Methodological Considerations for Studies in Sport and Exercise Science with Women as Participants",
     "doi": "10.1007/s40279-021-01435-8", "topics": ["research quality", "cycle", "women"]},
    {"pmcid": "PMC8794783", "ref": "Frampton et al., 2022", "year": 2022, "level": "randomized crossover trial",
     "title": "The acute effect of fasted exercise on energy intake, energy expenditure, subjective hunger and gastrointestinal hormone release",
     "doi": "10.1038/s41366-021-00993-1", "topics": ["fasted exercise", "appetite", "energy"]},
    {"pmcid": "PMC12855119", "ref": "Frontiers in Physiology, 2025", "year": 2025, "level": "randomized crossover trial",
     "title": "Fasting vs. post-breakfast Tabata exercise: substrate metabolism and energy expenditure",
     "doi": "10.3389/fphys.2025.1721312", "topics": ["fasted exercise", "metabolism"]},
]

BY_PMCID = {p["pmcid"]: p for p in PAPERS}
