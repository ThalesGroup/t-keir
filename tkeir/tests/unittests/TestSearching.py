# -*- coding: utf-8 -*-
"""Convert source document to tkeir indexer document
Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2020 by THALES
"""
import unittest
import json
import os
import py7zr
from thot.tasks.searching.SearchingConfiguration import SearchingConfiguration
from thot.tasks.searching.Searching import Searching
from thot.core.ThotLogger import ThotLogger, LogUserContext


class TestSearching(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        dir_path = os.path.dirname(os.path.realpath(__file__))
        self.data_path = os.path.abspath(os.path.join(dir_path, "../data/test-index"))
        try:
            with py7zr.SevenZipFile(os.path.join(self.data_path, "index4test.json.7z"), mode="r") as z:
                z.extractall(path=self.data_path)
                os.system(os.path.join(self.data_path, "create-index.sh"))
        except Exception as e:
            print(str(e))
        self.opendistro_host = "opendistro"
        if "OPENDISTRO_DNS_HOST" in os.environ:
            self.opendistro_host = os.environ["OPENDISTRO_DNS_HOST"]
        searchingConfig = SearchingConfiguration()
        with open("/home/tkeir_svc/tkeir/app/projects/default/configs/search.json", encoding="utf-8") as search_f:
            searchingConfig.load(search_f)
            ThotLogger.loads(searchingConfig.logger_config.configuration)
            search_f.close()
        searchingConfig.configuration["document-index-name"] = "text-index-test"
        if "qa" in searchingConfig.configuration:
            del searchingConfig.configuration["qa"]
        self.search = Searching(searchingConfig)

    @classmethod
    def tearDownClass(self):
        os.system(os.path.join(self.data_path, "destroy-index.sh"))

    def test_querying_with_doc(self):
        doc = {
            "content": '(EP2257590)|1. Compositions comprising A) from 10 to 99 parts by weight, in each case based on the entirety of components A+B+C, of aromatic polycarbonate and/or aromatic polyester carbonate, B) from 1 to 35 parts by weight, in each case based on the entirety of components A+B+C, of rubber-modified graft polymer of B.1 from 5 to 95 wt.% of at least one vinyl monomer on B.2 from 95 to 5 wt.% of one or more graft bases having a glass transition temperature < 10\u0106, C) from 0 to 40 parts by weight, in each case based on the entirety of components A+B+C, of resinous, thermoplastic and rubber-free vinyl (co)polymer and/or polyalkylene terephthalate, D) from 0 to 50 parts by weight, in each case based on the entirety of components A+B+C, of phosphorus-containing flame retardant, E) from 0 to 1.0 part by weight, in each case based on the entirety of components A+B+C, of acidic additives and F) from 0 to 50 parts by weight, in each case based on the entirety of components A+B+C, of additional substances, wherein component B is obtainable by reacting component B.1 with the graft base B.2 by means of emulsion polymerisation, with the proviso that, in the case of compositions that are free of components D) and E), the pH of the graft polymer dispersion during the precipitation step is less than 7, characterised in that the graft reaction uses from 0.1 to 5 parts by weight (based on the entirety of the parts by weight of the monomers B.1 used and of the graft base B.2 = 100 parts by weight) of at least one emulsifier selected from the group of the alkali metal salts of capric acid (C9H19COOH), lauric acid (C11H23COOH), myristic acid (C13H27COOH), palmitic acid (C15H31COOH), margaric acid (C16H33COOH), stearic acid (C17H35COOH), arachic acid (C19H39COOH), behenic acid (C21H43COOH), lignoceric acid (C23H47COOH) or cerotic acid (C25H51COOH), and the graft polymer is precipitated from the dispersion by addition of magnesium sulphate, where the emulsifier or emulsifiers and magnesium sulphate remain in component B.|4. Process for the preparation of impact-modified polycarbonate moulding compositions which have an improved natural colour while the good hydrolytic stability and processing stability of the impact-modified polycarbonate moulding compositions are retained, where the constituents A) from 10 to 99 parts by weight of aromatic polycarbonate and/or aromatic polyester carbonate, B) from 1 to 35 parts by weight of rubber-modified graft polymer of B.1 from 5 to 95 wt.% of at least one vinyl monomer on B.2 from 95 to 5 wt.% of one or more graft bases having a glass transition temperature < 10\u0106, C) from 0 to 40 parts by weight of resinous, thermoplastic and rubber-free vinyl (co)polymer and/or polyalkylene terephthalate, D) from 0 to 50 parts by weight, in each case based on the entirety of components A+B+C, of phosphorus-containing flame retardant, E) from 0 to 1.0 part by weight, in each case based on the entirety of components A+B+C, of acidic additives, and F) from 0 to 50 parts by weight, in each case based on the entirety of components A+B+C, of additional substances, are mixed in a known manner (either in succession or simultaneously, either at about 20\u0106 (room temperature) or at a higher temperature) and, at temperatures of from 260\u0106 to 300\u0106 in conventional assemblies such as internal mixers, extruders and twin-screw systems, are compounded in the melt and are extruded in the melt, characterised in that impact modifier used comprises rubber-modified graft polymer (component B) which is prepared by reacting component B.1 with the graft base B.2 by means of emulsion polymerisation, where (i) in the first step, the rubber base B.2 is prepared directly in the form of an aqueous dispersion by means of free-radical emulsion polymerisation or is dispersed in the water, (ii) in the second step, the reaction of component B.1 with the graft base B.2 (referred to hereinbelow as "graft reaction") is carried out by means of emulsion polymerisation, where 1) component B.2 dispersed in water, 2) from 0.1 to 5 parts by weight (based on the entirety of the parts by weight of the monomers B.1 used in the preparation of the graft polymer B and of the graft base B.2 = 100 parts by weight) of at least one emulsifier selected from the group of the alkali metal salts of capric acid (C9H19COOH), lauric acid (C11H23COOH), myristic acid (C13H27COOH), palmitic acid (C15H31COOH), margaric acid (C16H33COOH), stearic acid (C17H35COOH), arachic acid (C19H39COOH), behenic acid (C21H43COOH), lignoceric acid (C23H47COOH) or cerotic acid (C25H51COOH) are used, and the monomers according to component B.1 and free-radical generators and optionally molecular weight regulators are added to the rubber base dispersion obtained in step (1), 3) work-up is carried out by means of a process comprising the steps 3.1) precipitation with magnesium sulphate and 3.2) separation of the dispersing water, with the proviso that, in the case of compositions that are free of components D) and E), the pH of the graft polymer dispersion during the precipitation step (3.1) is less than 7, characterised in that the resulting moist graft polymer is not washed with additional water, where the emulsifier or emulsifiers and magnesium sulphate remain in component B.',
            "from": 0,
            "size": 5,
        }
        res = self.search.querying_with_doc(doc)
        self.assertEqual(res["items"][0]["_id"], "cacheid_d7ca2d6ff60cae9f6d320394407f7f1d")

    def test_querying_with_sentence(self):
        query = {"content": "what is light calcium carbonate ?", "from": 0, "size": 5}
        log_context = LogUserContext("autogenerated-xxx")
        res = self.search.querying_with_sentence(query, call_context=log_context)
        self.assertEqual(res["items"][0]["_id"], "cacheid_14da23ff80595e43175d3d0160424d59")

    def test_querying_with_sentence_and_options(self):
        query = {
            "content": "what is light calcium carbonate ?",
            "options": {
                "disable": ["qa", "aggregator"],
                "exclude": ["kg", "text_suggester", "content", "lemma_content", "summary", "lemma_title", "categories"],
            },
            "add-clause": {"type": "must", "clause": {"match": {"content": "calcium"}}},
            "from": 0,
            "size": 5,
        }
        log_context = LogUserContext("autogenerated-xxx")
        res = self.search.querying_with_sentence(query, call_context=log_context)
        self.assertEqual(res["items"][0]["_id"], "cacheid_14da23ff80595e43175d3d0160424d59")

    def test_custom(self):
        query = {
            "from": 0,
            "size": 10,
            "request": [
                {
                    "key": "content",
                    "value": '(EP2257590)|1. Compositions comprising A) from 10 to 99 parts by weight, in each case based on the entirety of components A+B+C, of aromatic polycarbonate and/or aromatic polyester carbonate, B) from 1 to 35 parts by weight, in each case based on the entirety of components A+B+C, of rubber-modified graft polymer of B.1 from 5 to 95 wt.% of at least one vinyl monomer on B.2 from 95 to 5 wt.% of one or more graft bases having a glass transition temperature < 10\u0106, C) from 0 to 40 parts by weight, in each case based on the entirety of components A+B+C, of resinous, thermoplastic and rubber-free vinyl (co)polymer and/or polyalkylene terephthalate, D) from 0 to 50 parts by weight, in each case based on the entirety of components A+B+C, of phosphorus-containing flame retardant, E) from 0 to 1.0 part by weight, in each case based on the entirety of components A+B+C, of acidic additives and F) from 0 to 50 parts by weight, in each case based on the entirety of components A+B+C, of additional substances, wherein component B is obtainable by reacting component B.1 with the graft base B.2 by means of emulsion polymerisation, with the proviso that, in the case of compositions that are free of components D) and E), the pH of the graft polymer dispersion during the precipitation step is less than 7, characterised in that the graft reaction uses from 0.1 to 5 parts by weight (based on the entirety of the parts by weight of the monomers B.1 used and of the graft base B.2 = 100 parts by weight) of at least one emulsifier selected from the group of the alkali metal salts of capric acid (C9H19COOH), lauric acid (C11H23COOH), myristic acid (C13H27COOH), palmitic acid (C15H31COOH), margaric acid (C16H33COOH), stearic acid (C17H35COOH), arachic acid (C19H39COOH), behenic acid (C21H43COOH), lignoceric acid (C23H47COOH) or cerotic acid (C25H51COOH), and the graft polymer is precipitated from the dispersion by addition of magnesium sulphate, where the emulsifier or emulsifiers and magnesium sulphate remain in component B.|4. Process for the preparation of impact-modified polycarbonate moulding compositions which have an improved natural colour while the good hydrolytic stability and processing stability of the impact-modified polycarbonate moulding compositions are retained, where the constituents A) from 10 to 99 parts by weight of aromatic polycarbonate and/or aromatic polyester carbonate, B) from 1 to 35 parts by weight of rubber-modified graft polymer of B.1 from 5 to 95 wt.% of at least one vinyl monomer on B.2 from 95 to 5 wt.% of one or more graft bases having a glass transition temperature < 10\u0106, C) from 0 to 40 parts by weight of resinous, thermoplastic and rubber-free vinyl (co)polymer and/or polyalkylene terephthalate, D) from 0 to 50 parts by weight, in each case based on the entirety of components A+B+C, of phosphorus-containing flame retardant, E) from 0 to 1.0 part by weight, in each case based on the entirety of components A+B+C, of acidic additives, and F) from 0 to 50 parts by weight, in each case based on the entirety of components A+B+C, of additional substances, are mixed in a known manner (either in succession or simultaneously, either at about 20\u0106 (room temperature) or at a higher temperature) and, at temperatures of from 260\u0106 to 300\u0106 in conventional assemblies such as internal mixers, extruders and twin-screw systems, are compounded in the melt and are extruded in the melt, characterised in that impact modifier used comprises rubber-modified graft polymer (component B) which is prepared by reacting component B.1 with the graft base B.2 by means of emulsion polymerisation, where (i) in the first step, the rubber base B.2 is prepared directly in the form of an aqueous dispersion by means of free-radical emulsion polymerisation or is dispersed in the water, (ii) in the second step, the reaction of component B.1 with the graft base B.2 (referred to hereinbelow as "graft reaction") is carried out by means of emulsion polymerisation, where 1) component B.2 dispersed in water, 2) from 0.1 to 5 parts by weight (based on the entirety of the parts by weight of the monomers B.1 used in the preparation of the graft polymer B and of the graft base B.2 = 100 parts by weight) of at least one emulsifier selected from the group of the alkali metal salts of capric acid (C9H19COOH), lauric acid (C11H23COOH), myristic acid (C13H27COOH), palmitic acid (C15H31COOH), margaric acid (C16H33COOH), stearic acid (C17H35COOH), arachic acid (C19H39COOH), behenic acid (C21H43COOH), lignoceric acid (C23H47COOH) or cerotic acid (C25H51COOH) are used, and the monomers according to component B.1 and free-radical generators and optionally molecular weight regulators are added to the rubber base dispersion obtained in step (1), 3) work-up is carried out by means of a process comprising the steps 3.1) precipitation with magnesium sulphate and 3.2) separation of the dispersing water, with the proviso that, in the case of compositions that are free of components D) and E), the pH of the graft polymer dispersion during the precipitation step (3.1) is less than 7, characterised in that the resulting moist graft polymer is not washed with additional water, where the emulsifier or emulsifiers and magnesium sulphate remain in component B.',
                },
                {"key": "kg", "value": {"subject": "b29c-048/40", "value": "cpc", "property": "rel:is_a"}},
            ],
            "output": {"source": [{"name": ["content"], "join": "|"}], "score": True},
        }
        res = self.search.custom_structured_query(query)
        self.assertEqual(
            res[0]["title"][0],
            "Compositions de polycarbonate thermoplastique, procédé de fabrication et procédé d utilisation correspondants",
        )
