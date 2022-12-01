
# -*- coding: utf-8 -*-
"""Data management and generation

Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""

import os
import sys
import json
import argparse
import string
from tqdm import tqdm
import traceback
import pandas as pd

class_map = {
    "/business/person/company": "work_at",
    "Entity-Origin(e1,e2)": "entity_origin",
    "/location/country/languages_spoken": "country_language",
    "competition class": "competition_class",
    "Cause-Effect(e2,e1)": "cause_effect",
    "Message-Topic(e1,e2)": "message_topic",
    "/location/administrative_division/country": "location",
    "P123": "publisher",
    "/sports/sports_team/location": "location",
    "/film/film/featured_film_locations": "location",
    "/people/person/nationality": "nationality",
    "nationality": "nationality",
    "P106": "occupation",
    "P412": "voice_type",
    "/people/person/religion": "regilion",
    "occupant": "occupant",
    "/people/person/ethnicity": "ethnicity",
    "notable work": "notable_work",
    "has part": "has_part",
    "/people/ethnicity/includes_groups": "ethnicity_group",
    "P2094": None,
    "characters": "characters",
    "P931": "transport_hub",
    "P26": "spouse",
    "P1408": "media_diffusion",
    "director": "director",
    "position played on team / speciality": "speciality",
    "architect": "architect",
    "after a work by": "after_work_by",
    "follows": "follows",
    "P58": "screenwriter",
    "Member-Collection(e1,e2)": "member_collection",
    "spouse": "spouse",
    "Instrument-Agency(e2,e1)": "agency_instrument",
    "Instrument-Agency(e1,e2)": "instrument_agency",
    "father": "father",
    "P991": "successful_candidate",
    "owned by": "owned_by",
    "P674": "characters",
    "field of work": "field_of_work",
    "/people/family/members": "family_member",
    "successful candidate": "successful_candidate",
    "tributary": "tributary",
    "P241": "military_branch",
    "place served by transport hub": "transport_hub",
    "mouth of the watercourse": "mouth_of_the_watercourse",
    "subsidiary": "subsidiary",
    "P25": "mother",
    "occupation": "occupation",
    "crosses": "crosses",
    "said to be the same as": "said_to_be_the_same_as",
    "Entity-Origin(e2,e1)": "origin_entity",
    "P3373": "sibling",
    "P740": "location",
    "/business/business_location/parent_company": "location",
    "P57": "director",
    "located in or next to body of water": "location",
    "/business/shopping_center/owner": "owner",
    "P135": "movement",
    "/location/in_state/judicial_capital": "capital",
    "P1303": "instrument",
    "/business/company/majorshareholders": "shareholder",
    "platform": "platform",
    "sibling": "sibling",
    "Other": "other",
    "sports season of league or competition": "competition",
    "P527": "has_part",
    "P137": "operator",
    "P1411": "nominated_for",
    "P1001": "applies_to_jurisdiction",
    "composer": "composer",
    "P86": "composer",
    "P400": "platform",
    "member of": "member_of",
    "P937": "location",
    "headquarters location": "location",
    "developer": "developer",
    "distributor": "distributor",
    "P306": "operation_system",
    "religion": "religion",
    "/people/family/country": "location",
    "performer": "performer",
    "part of": "part_of",
    "/location/jp_prefecture/capital": "capital",
    "P1346": "winner",
    "Member-Collection(e2,e1)": "collection-member",
    "/people/profession/people_with_this_profession": "profession",
    "P974": "tributary",
    "work location": "location",
    "P102": "member_of_political_party",
    "participant": "participant",
    "movement": "movement",
    "mountain range": "mountain_range",
    "/sports/sports_team_location/teams": "location",
    "P1877": "after_work_by",
    "member of political party": "member_of_political_party",
    "P101": "field_of_work",
    "P495": "country_of_origin",
    "child": "child",
    "publisher": "publisher",
    "/base/locations/countries/states_provinces_within": "location",
    "followed by": "followed_by",
    "P39": "position_held",
    "P706": "location",
    "/people/deceased_person/place_of_burial": "place_of_death",
    "/film/film_festival/location": "location",
    "Entity-Destination(e1,e2)": "entity_destination",
    "nominated for": "nominated_for",
    "P403": "mouth_of_the_watercourse",
    "manufacturer": "manufacturer",
    "instrument": "instrument",
    "/business/location": "location",
    "/business/company_shareholder/major_shareholder_of": "shareholder",
    "participating team": "participating_team",
    "/location/country/administrative_divisions": "location",
    "P118": "league",
    "/location/de_state/capital": "capital",
    "/people/deceased_person/place_of_death": "place_of_death",
    "/location/in_state/legislative_capital": "capital",
    "country": "country",
    "/location/country/capital": "capital",
    "P155": "follows",
    "/location/us_county/county_seat": None,
    "/business/company/locations": "location",
    "original network": "original_network",
    "P641": "sport",
    "/people/person/profession": "profession",
    "participant of": "participant_of",
    "/people/ethnicity/geographic_distribution": "geographic_distribution",
    "P460": "said_to_be_the_same_as",
    "P27": "country_of_citizenship",
    "/location/province/capital": "capital",
    "located on terrain feature": "located_on_terrain_feature",
    "Product-Producer(e2,e1)": "producer_product",
    "located in the administrative territorial entity": "location",
    "voice type": "voice_type",
    "P159": "headquarters_location",
    "applies to jurisdiction": "applies_to_jurisdiction",
    "Product-Producer(e1,e2)": "product_producer",
    "Component-Whole(e1,e2)": "component_while",
    "/time/event/locations": "event_location",
    "P364": "original_language",
    "head of government": "head_of_government",
    "contains administrative territorial entity": None,
    "/business/company/advisors": "advisor",
    "/film/film_location/featured_in_films": "location",
    "P59": "constellation",
    "heritage designation": "heritage_designation",
    "P6": "head_of_government",
    "P156": "followed_by",
    "position held": "position_held",
    "P3450": "competition",
    "original language of film or TV show": "original_language",
    "/location/br_state/capital": "capital",
    "P463": "member_of",
    "/people/person/place_of_birth": "place_of_birth",
    "/location/in_state/administrative_capital": "capital",
    "Cause-Effect(e1,e2)": "cause_effect",
    "/business/company_advisor/companies_advised": "advised",
    "P206": "location",
    "operating system": "operation_system",
    "military branch": "military_branch",
    "constellation": "constellation",
    "NA": None,
    "/location/region/capital": "capital",
    "P31": "instance_of",
    "/location/mx_state/capital": "capital",
    "Entity-Destination(e2,e1)": "designation_entity",
    "/business/company/major_shareholders": "shareholder",
    "genre": "genre",
    "P177": "crosses",
    "military rank": "military_rank",
    "/people/person/children": "child",
    "/location/neighborhood/neighborhood_of": "neighborhood_of",
    "/location/fr_region/capital": "capital",
    "P40": "child",
    "P140": "religion",
    "mother": "mother",
    "/location/us_state/capital": "capital",
    "P921": "main_subject",
    "P136": "genre",
    "instance of": "instance_of",
    "P1435": "heritage_designation",
    "location": "location",
    "Message-Topic(e2,e1)": "topic_message",
    "language of work or name": "language_of_work",
    "P1344": "participant_in",
    "/business/company/industry": "industry",
    "P105": "taxon_rank",
    "/business/company/founders": "founder",
    "P22": "father",
    "P1923": "participating_team",
    "/people/deceased_person/place_of_death": "place_of_death",
    "/business/company/place_founded": "place",
    "country of citizenship": "country_of_citizenship",
    "licensed to broadcast to": "licensed_to_broadcast_to",
    "P750": "distributor",
    "P466": "occupant",
    "main subject": "main_subject",
    "/business/shopping_center_owner/shopping_centers_owned": None,
    "/broadcast/content/location": "location",
    "winner": "winner",
    "P710": "participant",
    "Content-Container(e1,e2)": "content_container",
    "P4552": "mountain_range",
    "P131": "location",
    "P449": "original_broadcaster",
    "Component-Whole(e2,e1)": "whole_component",
    "P407": "language_of_work",
    "P127": "owner",
    "operator": "operator",
    "P17": "country",
    "P413": "speciality",
    "P178": "developer",
    "P410": "military_rank",
    "P276": "location",
    "residence": "residence",
    "P84": "architect",
    "P361": "part_of",
    "taxon rank": "taxon_rank",
    "P175": "performer",
    "P176": "manufacturer",
    "screenwriter": "screenwriter",
    "/location/location/contains": "contains",
    "P551": "residence",
    "country of origin": "country_of_origin",
    "P800": "notable_work",
    "/location/cn_province/capital": "capital",
    "P355": "subsidiary",
    "league": "league",
    "P264": "record_label",
    "P150": None,
    "/people/deceased_person/place_of_burial": "location",
    "sport": "sport",
    "/people/ethnicity/people": None,
    "/people/ethnicity/included_in_group": "included_in_group",
    "/broadcast/producer/location": "location",
    "/people/person/place_lived": "location",
    "location of formation": "location",
    "Content-Container(e2,e1)": "contain_content",
    "record label": "record_label",
    "/location/it_region/capital": "capital",
    "/people/place_of_interment/interred_here": "location",
}


def write_in_file(jsonl_f, output_df, lang):
    json_lines = jsonl_f.read().split("\n")
    prepared_data = []
    for json_str in json_lines:
        try:
            json_data = json.loads(json_str)
            if "token" in json_data:
                sentence = json_data["token"]
                json_data["tag"] = ["_"] * len(sentence)
                for i in range(json_data["h"]["pos"][0], json_data["h"]["pos"][1]):
                    json_data["tag"][i] = "S"
                for i in range(json_data["t"]["pos"][0], json_data["t"]["pos"][1]):
                    if (json_data["relation"] in class_map) and class_map[json_data["relation"]]:
                        json_data["tag"][i] = class_map[json_data["relation"]]
            if "text" in json_data:
                sentence = json_data["text"]
                sentence = " ".join(sentence.strip().split())
                json_data["text"] = sentence
                json_data["tag"] = ["_"] * len(sentence)
                for ci in range(len(sentence)):
                    if sentence[ci] == " ":
                        json_data["tag"][ci] = " "
                for i in range(json_data["h"]["pos"][0], json_data["h"]["pos"][1]):
                    json_data["tag"][i] = "S"
                for i in range(json_data["t"]["pos"][0], json_data["t"]["pos"][1]):
                    if (json_data["relation"] in class_map) and class_map[json_data["relation"]]:
                        json_data["tag"][i] = class_map[json_data["relation"]]
                start_merge = 0
                tags = []
                for t in range(len(sentence)):
                    if sentence[t] == " ":
                        tags.append(json_data["tag"][start_merge])
                        start_merge = t + 1
                if start_merge != len(sentence):
                    tags.append(json_data["tag"][start_merge])
                sentence = sentence.split()
                json_data["tag"] = tags
            if len(sentence) == len(json_data["tag"]):
                ndf = pd.DataFrame(
                    [
                        [
                            "relation",
                            lang,
                            " ".join(sentence).replace("\t", " ").strip(),
                            " ".join(json_data["tag"]).replace("\t", " ").strip(),
                        ]
                    ],
                    columns=["prefix", "language", "input_text", "target_text"],
                )
                output_df = pd.concat([output_df, ndf])
            else:
                print("Bad len *********************")

        except Exception as e:
            print(e, traceback.format_exc())
    return output_df


def main(args):
    train = []
    test = []
    dev = []
    for (dirpath, dirnames, filenames) in os.walk(args.input):
        for filename in filenames:
            if filename.endswith(".txt") and ("train" in filename.lower()):
                train.append(os.path.join(dirpath, filename))
            elif filename.endswith(".txt") and ("test" in filename.lower()):
                test.append(os.path.join(dirpath, filename))
            elif filename.endswith(".txt") and ("val" in filename.lower()):
                dev.append(os.path.join(dirpath, filename))
    train_files = tqdm(train)
    test_files = tqdm(test)
    dev_files = tqdm(dev)
    train_df = pd.DataFrame(columns=["prefix", "language", "input_text", "target_text"]).astype(str)
    dev_df = pd.DataFrame(columns=["prefix", "language", "input_text", "target_text"]).astype(str)
    test_df = pd.DataFrame(columns=["prefix", "language", "input_text", "target_text"]).astype(str)
    for file in train_files:
        lang = "en"
        print("Train Language:", lang)
        with open(file, "r", encoding="utf-8") as conllu_f:
            train_df = write_in_file(conllu_f, train_df, lang)
            conllu_f.close()
    train_df.to_csv(
        args.output + "-train.tsv",
        index=False,
        sep="\t",
        encoding="utf-8",
        columns=["prefix", "language", "input_text", "target_text"],
    )
    for file in test_files:
        lang = "en"
        print("Test Language:", lang)
        with open(file, "r", encoding="utf-8") as conllu_f:
            test_df = write_in_file(conllu_f, test_df, lang)
            conllu_f.close()
    test_df.reset_index().to_csv(
        args.output + "-test.tsv",
        index=False,
        sep="\t",
        encoding="utf-8",
        columns=["prefix", "language", "input_text", "target_text"],
    )
    for file in dev_files:
        lang = "en"
        print("Dev Language:", lang)
        with open(file, "r", encoding="utf-8") as conllu_f:
            dev_df = write_in_file(conllu_f, dev_df, lang)
            conllu_f.close()
    dev_df.to_csv(
        args.output + "-dev.tsv",
        index=False,
        sep="\t",
        encoding="utf-8",
        columns=["prefix", "language", "input_text", "target_text"],
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--input", default=None, type=str, help="UD framework directory")
    parser.add_argument("-o", "--output", default="./out", type=str, help="UD framework directory")
    main(parser.parse_args())
