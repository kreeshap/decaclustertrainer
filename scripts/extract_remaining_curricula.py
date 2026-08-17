"""Extract 2026-27 Hospitality, BMA, and Entrepreneurship curricula."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pdfplumber

from extract_finance_curriculum import ROOT, YEAR, extract_section, write_json


DATA = ROOT / "performance indicator jsons"
SHARED = DATA / "shared" / "business_administration_core_2026_27.json"


def slug(name: str) -> str:
    return name.lower().replace("+", "and").replace("-", "_").replace(" ", "_")


def usage(exam, performance=None, component="roleplay"):
    return {"exam": {"curriculum": exam}, component: None if performance is None else {"curriculum": performance}}


def prove_and_add_shared(core: dict) -> None:
    shared = json.loads(SHARED.read_text(encoding="utf-8"))
    fields = ("code", "level", "official_text", "instructional_area_code", "instructional_area_name", "standard", "performance_element")
    if [[x[k] for k in fields] for x in shared["performance_indicators"]] != [[x[k] for k in fields] for x in core["performance_indicators"]]:
        raise ValueError(f"{core['cluster']} Tier 1 differs from the shared Business Administration Core")
    for existing, incoming in zip(shared["performance_indicators"], core["performance_indicators"]):
        sources = existing.setdefault("sources", [dict(existing["source"])])
        if incoming["source"] not in sources:
            sources.append(dict(incoming["source"]))
    write_json(SHARED, shared)


def extract_standard(source: Path, key: str, cluster: str, document: str, specs, event_defs, blueprint) -> None:
    base = DATA / key
    with pdfplumber.open(source) as pdf:
        datasets = [(filename, extract_section(pdf, pages, tier, cid, label, pathway, cluster=cluster, document_id=document)) for filename, pages, tier, cid, label, pathway in specs]
    prove_and_add_shared(datasets[0][1])
    for filename, dataset in datasets[1:]:
        write_json(base / "curriculum" / filename, dataset)
    focus = {"competitive_year": YEAR, "status": "pending", "released_at": None, "instructional_areas": []}
    for code, event in event_defs.items():
        write_json(base / "events" / f"{code}.json", {"schema_version": 1, "cluster": cluster, "competitive_year": YEAR, "event_id": slug(event["name"]), "event_code": code, "district_focus": focus, **event})
    write_json(base / "exam_blueprint.json", {"schema_version": 1, "competitive_year": YEAR, "exam": cluster, "item_count": 100, "actual_counts_may_vary_slightly": True, "source": {"document": "2026-27-HS-Competitive-Events-Exam-Blueprint", "page": 39}, "instructional_areas": blueprint})
    write_json(base / "manifest.json", {"schema_version": 1, "cluster": cluster, "competitive_year": YEAR, "source_document": f"source/{document}.pdf", "exam_blueprint": "exam_blueprint.json", "curriculum": ["../shared/business_administration_core_2026_27.json"] + [f"curriculum/{x[0]}" for x in datasets[1:]], "events": [f"events/{x}.json" for x in event_defs], "counts": {d["curriculum_id"]: len(d["performance_indicators"]) for _, d in datasets}})
    (base / "source").mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, base / "source" / f"{document}.pdf")
    print(key, {d["curriculum_id"]: len(d["performance_indicators"]) for _, d in datasets})


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit("Pass Hospitality, BMA, and Entrepreneurship PDF paths")
    core = "business_administration_core_2026_27"
    h2 = "hospitality_tier2"; hs = [core, h2]
    hospitality_specs = [
        ("tier1_business_admin.json", range(4,21),1,core,"Business Administration Core",None),
        ("tier2_hospitality.json", range(21,30),2,h2,"Hospitality and Tourism Career Cluster",None),
        ("tier3_event_management.json", range(30,38),3,"hospitality_tier3_event_management","Event Management Pathway","Event Management"),
        ("tier3_lodging.json", range(38,44),3,"hospitality_tier3_lodging","Lodging Pathway","Lodging"),
        ("tier3_restaurant_management.json", range(44,50),3,"hospitality_tier3_restaurant","Restaurant Management Pathway","Restaurant Management"),
        ("tier3_travel_tourism.json", range(50,59),3,"hospitality_tier3_travel_tourism","Travel and Tourism Pathway","Travel and Tourism"),
    ]
    he = {
        "HLM":{"name":"Hotel and Lodging Management Series","event_type":"individual_series","curriculum_usage":usage(hs,hs+["hospitality_tier3_lodging"]),"study_curriculum":hs+["hospitality_tier3_lodging"]},
        "QSRM":{"name":"Quick Serve Restaurant Management Series","event_type":"individual_series","curriculum_usage":usage(hs,hs+["hospitality_tier3_restaurant"]),"study_curriculum":hs+["hospitality_tier3_restaurant"]},
        "RFSM":{"name":"Restaurant and Food Service Management Series","event_type":"individual_series","curriculum_usage":usage(hs,hs+["hospitality_tier3_restaurant"]),"study_curriculum":hs+["hospitality_tier3_restaurant"]},
        "HTDM":{"name":"Hospitality Services Team Decision Making","event_type":"team_decision_making","curriculum_usage":usage(hs,hs,"case_study"),"study_curriculum":hs},
        "TTDM":{"name":"Travel and Tourism Team Decision Making","event_type":"team_decision_making","curriculum_usage":usage(hs,hs,"case_study"),"study_curriculum":hs},
        "PHT":{"name":"Principles of Hospitality and Tourism","event_type":"principles","curriculum_usage":usage([core],[core]),"study_curriculum":[core]},
        "HTPS":{"name":"Hospitality and Tourism Professional Selling","event_type":"exam_only","curriculum_usage":usage(hs,None),"study_curriculum":hs},
    }
    hb=[("Business Law",3,3,2),("Communications",5,4,3),("Customer Relations",8,9,9),("Economics",6,6,5),("Emotional Intelligence",9,9,7),("Entrepreneurship",1,0,0),("Financial Analysis",8,7,7),("Human Resources Management",2,1,1),("Information Management",14,15,15),("Knowledge Management",0,1,1),("Market Planning",1,1,2),("Marketing",1,1,2),("Operations",13,13,13),("Pricing",1,1,1),("Product/Service Management",6,7,9),("Professional Development",8,7,6),("Promotion",2,3,3),("Quality Management",1,1,1),("Risk Management",1,1,2),("Selling",7,8,9),("Strategic Management",3,2,2)]
    extract_standard(Path(sys.argv[1]),"hospitality","Hospitality + Tourism","2026-27-HS-DECA-Hospitality",hospitality_specs,he,[{"name":n,"district":d,"association":a,"icdc":i} for n,d,a,i in hb])

    b2="bma_tier2"; bs=[core,b2]
    bma_specs=[("tier1_business_admin.json",range(4,21),1,core,"Business Administration Core",None),("tier2_bma.json",range(21,25),2,b2,"Business Management and Administration Career Cluster",None),("tier3_administrative_services.json",range(25,31),3,"bma_tier3_administrative_services","Administrative Services Pathway","Administrative Services"),("tier3_business_information_management.json",range(31,36),3,"bma_tier3_business_information_management","Business Information Management Pathway","Business Information Management"),("tier3_general_management.json",range(36,40),3,"bma_tier3_general_management","General Management Pathway","General Management"),("tier3_human_resources.json",range(40,46),3,"bma_tier3_human_resources","Human Resources Management Pathway","Human Resources Management"),("tier3_operations.json",range(46,54),3,"bma_tier3_operations","Operations Pathway","Operations")]
    be={"BLTDM":{"name":"Business Law and Ethics Team Decision Making","event_type":"team_decision_making","curriculum_usage":usage(bs,bs,"case_study"),"study_curriculum":bs},"HRM":{"name":"Human Resources Management Series","event_type":"individual_series","curriculum_usage":usage(bs,bs+["bma_tier3_human_resources"]),"study_curriculum":bs+["bma_tier3_human_resources"]},"PBM":{"name":"Principles of Business Management and Administration","event_type":"principles","curriculum_usage":usage([core],[core]),"study_curriculum":[core]}}
    bb=[("Business Law",5,5,5),("Communications",7,6,6),("Customer Relations",2,2,1),("Economics",6,5,4),("Emotional Intelligence",9,8,6),("Entrepreneurship",1,0,0),("Financial Analysis",7,6,5),("Human Resources Management",1,0,0),("Information Management",7,6,6),("Knowledge Management",6,7,8),("Marketing",1,1,1),("Operations",21,24,26),("Professional Development",6,5,4),("Project Management",6,7,8),("Quality Management",3,4,5),("Risk Management",4,5,5),("Strategic Management",8,9,10)]
    extract_standard(Path(sys.argv[2]),"business_management","Business Management + Administration","2026-27-HS-DECA-BMA",bma_specs,be,[{"name":n,"district":d,"association":a,"icdc":i} for n,d,a,i in bb])
    extract_entrepreneurship(Path(sys.argv[3]))


def extract_entrepreneurship(source: Path) -> None:
    base=DATA/"entrepreneurship"; document="2026-27-HS-DECA-Entrepreneurship"
    specs=[("business_administration_core.json",range(2,11),"entrepreneurship_business_administration_core","Business Administration Core"),("business_management_administration_core.json",range(11,13),"entrepreneurship_business_management_core","Business Management and Administration Core"),("finance_core.json",range(13,14),"entrepreneurship_finance_core","Finance Core"),("marketing_core.json",range(14,17),"entrepreneurship_marketing_core","Marketing Core")]
    with pdfplumber.open(source) as pdf:
        datasets=[(f,extract_section(pdf,pages,None,cid,label,None,cluster="Entrepreneurship",document_id=document,curriculum_section=label)) for f,pages,cid,label in specs]
    for f,d in datasets: write_json(base/"curriculum"/f,d)
    ids=[d["curriculum_id"] for _,d in datasets]
    focus={"competitive_year":YEAR,"status":"pending","released_at":None,"instructional_areas":[]}
    events={"ENT":("Entrepreneurship Series","roleplay"),"ETDM":("Entrepreneurship Team Decision Making","case_study")}
    for code,(name,component) in events.items(): write_json(base/"events"/f"{code}.json",{"schema_version":1,"cluster":"Entrepreneurship","competitive_year":YEAR,"event_id":slug(name),"event_code":code,"name":name,"event_type":"individual_series" if code=="ENT" else "team_decision_making","district_focus":focus,"curriculum_usage":usage(ids,ids,component),"study_curriculum":ids})
    eb=[("Business Law",4,4,3),("Channel Management",3,3,3),("Communications",1,0,1),("Customer Relations",1,1,1),("Economics",3,3,2),("Emotional Intelligence",6,6,4),("Entrepreneurship",14,13,14),("Financial Analysis",10,9,11),("Human Resources Management",5,4,4),("Information Management",4,3,2),("Market Planning",5,6,6),("Marketing",1,1,1),("Marketing-Information Management",2,3,2),("Operations",13,13,14),("Pricing",2,3,2),("Product/Service Management",4,4,4),("Professional Development",5,5,4),("Promotion",6,7,8),("Quality Management",1,1,1),("Risk Management",2,3,4),("Selling",1,1,1),("Strategic Management",7,7,8)]
    write_json(base/"exam_blueprint.json",{"schema_version":1,"competitive_year":YEAR,"exam":"Entrepreneurship","item_count":100,"actual_counts_may_vary_slightly":True,"source":{"document":"2026-27-HS-Competitive-Events-Exam-Blueprint","page":39},"instructional_areas":[{"name":n,"district":d,"association":a,"icdc":i} for n,d,a,i in eb]})
    write_json(base/"manifest.json",{"schema_version":1,"cluster":"Entrepreneurship","curriculum_family":"sectioned","competitive_year":YEAR,"source_document":f"source/{document}.pdf","exam_blueprint":"exam_blueprint.json","curriculum":[f"curriculum/{f}" for f,_ in datasets],"events":["events/ENT.json","events/ETDM.json"],"counts":{d["curriculum_id"]:len(d["performance_indicators"]) for _,d in datasets}})
    (base/"source").mkdir(parents=True,exist_ok=True); shutil.copy2(source,base/"source"/f"{document}.pdf")
    print("entrepreneurship",{d["curriculum_id"]:len(d["performance_indicators"]) for _,d in datasets})


if __name__ == "__main__": main()
