# -*- coding: utf-8 -*-
"""Relation clustering
Author : Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""

import requests
import json
from tkeir.thot.core.ThotLogger import ThotLogger
from thot.tasks.relations.RelationClusterizerConfiguration import RelationClusterizerConfiguration
from thot.tasks.relations.RelationsClusterizer import RelationsClusterizer
from thot.tasks.embeddings.Embeddings import Embeddings
from thot.tasks.embeddings.EmbeddingsConfiguration import EmbeddingsConfiguration


class ClusteringInference:
    def runEmbeddingsDecorator(self, sentences, call_context=None):
        emb = []
        if self.embeddings:
            emb = self.embeddings.computeFromTable(sentences)
        else:
            json_request = {"sentences": sentences}
            r = requests.post(
                self.scheme + "://" + self.emb_host + ":" + str(self.emb_port) + "/api/embeddings/run_from_table",
                json=json_request,
                verify=self.emb_verif,
            )
            if r.status_code == 200:
                emb = r.json()["results"]
            else:
                ThotLogger.error("Embeddings server does not return results", context=call_context)
        return emb

    def __init__(self, config: RelationClusterizerConfiguration, embeddings_server=False, call_context=None):
        self.config = config
        self.embeddings = None
        with open(config.configuration["clustering-model"]["semantic-quantizer-model"], "rb") as q_model_f:
            self.quantizerModel = RelationsClusterizer(model_file_handler=q_model_f)
            q_model_f.close()

        if embeddings_server:
            if "clustering-model" not in config.configuration:
                raise ValueError("Cluster Model is mandatory")
            if "semantic-quantizer-model" not in config.configuration["clustering-model"]:
                raise ValueError("Bad value of clustering-model")
            if "embeddings" not in config.configuration["cluster"]:
                raise ValueError("Embedding server should be definied")
            self.emb_host = config.configuration["cluster"]["embeddings"]["server"]["host"]
            self.emb_port = config.configuration["cluster"]["embeddings"]["server"]["port"]
            self.emb_verif = True
            self.scheme = "http"
            self.emb_verif = True
            if "no-verify-ssl" in config.configuration["cluster"]["embeddings"]["server"]:
                self.emb_verif = not config.configuration["cluster"]["embeddings"]["server"]["no-verify-ssl"]
            if ("use-ssl" in config.configuration["cluster"]["embeddings"]["server"]) and config.configuration["cluster"][
                "embeddings"
            ]["server"]["use-ssl"]:
                self.scheme = "https"
            ThotLogger.info(
                "Test embedding server health : "
                + self.scheme
                + "://"
                + self.emb_host
                + ":"
                + str(self.emb_port)
                + "/api/embeddings/health"
                + " ## "
                + str(self.emb_verif),
                context=call_context,
            )
            try:
                r = requests.get(
                    self.scheme + "://" + self.emb_host + ":" + str(self.emb_port) + "/api/embeddings/health",
                    verify=self.emb_verif,
                )
                if r.status_code != 200:
                    raise ValueError("Cannot connect to embeddings server")
            except Exception as e_req:
                ThotLogger.error(
                    "Connexion to embbedinds failed, this can cause service issues." + str(e_req), context=call_context
                )
        else:
            if "aggregate" in config.configuration["cluster"]["embeddings"]:
                embeddings_config = EmbeddingsConfiguration()
                with open(config.configuration["cluster"]["embeddings"]["aggregate"]["configuration"]) as fh:
                    embeddings_config.load(fh)
                    fh.close()
                self.embeddings = Embeddings(config=embeddings_config)
            else:
                raise ValueError("server or aggregate field is mandatory")

    def infer(self, tkeir_doc, call_context=None):
        nameClusterMapping = {"subject": "subject", "property": "relation", "value": "object"}
        semantic_need = {"subject": set(), "relation": set(), "object": set(), "keyword": set()}
        for kg_item in tkeir_doc["kg"]:
            no_position = False
            triple_items = dict()
            for triple_item in ["subject", "property", "value"]:
                if kg_item[triple_item]["positions"] == [-1]:
                    no_position = True
                if kg_item[triple_item]["lemma_content"]:
                    triple_items[triple_item] = " ".join(kg_item[triple_item]["lemma_content"])
                else:
                    triple_items[triple_item] = " ".join(kg_item[triple_item]["content"])
            if not no_position:
                for triple_item in ["subject", "property", "value"]:
                    semantic_need[nameClusterMapping[triple_item]].add(triple_items[triple_item])
        for kw_item in tkeir_doc["keywords"]:
            semantic_need["keyword"].add(kw_item["text"])
        embpred = {"subject": dict(), "relation": dict(), "object": dict(), "keyword": dict()}
        for triple_item in ["subject", "relation", "object", "keyword"]:
            emb = self.runEmbeddingsDecorator(list(semantic_need[triple_item]), call_context=call_context)
            for e_i in emb:
                pred = self.quantizerModel.predict([e_i["embedding"]], index=RelationsClusterizer.name2index[triple_item])
                embpred[triple_item][e_i["content"]] = pred[0]
                if triple_item == "keyword":
                    tkeir_doc["kg"].append(
                        {
                            "subject": {
                                "content": e_i["content"].split(" "),
                                "lemma_content": e_i["content"].split(" "),
                                "label": "",
                                "class": pred[0],
                                "positions": [0, 0],
                            },
                            "property": {
                                "content": ["rel:is_a"],
                                "lemma_content": ["rel:is_a"],
                                "label": "",
                                "class": -1,
                                "positions": [-1],
                            },
                            "value": {
                                "content": ["keyword"],
                                "lemma_content": ["keyword"],
                                "label": "",
                                "class": -1,
                                "positions": [-1],
                            },
                            "automatically_fill": True,
                            "confidence": 0.0,
                            "weight": 0.0,
                            "field_type": "keywords",
                        }
                    )

        for kg_item in tkeir_doc["kg"]:
            if " ".join(kg_item["subject"]["lemma_content"]) in embpred["subject"]:
                kg_item["subject"]["class"] = embpred["subject"][" ".join(kg_item["subject"]["lemma_content"])]
            elif " ".join(kg_item["subject"]["content"]) in embpred["subject"]:
                kg_item["subject"]["class"] = embpred["subject"][" ".join(kg_item["subject"]["content"])]

            if " ".join(kg_item["property"]["lemma_content"]) in embpred["relation"]:
                kg_item["property"]["class"] = embpred["relation"][" ".join(kg_item["property"]["lemma_content"])]
            elif " ".join(kg_item["property"]["content"]) in embpred["relation"]:
                kg_item["property"]["class"] = embpred["relation"][" ".join(kg_item["property"]["content"])]

            if " ".join(kg_item["value"]["lemma_content"]) in embpred["object"]:
                kg_item["value"]["class"] = embpred["object"][" ".join(kg_item["value"]["lemma_content"])]
            elif " ".join(kg_item["value"]["content"]) in embpred["object"]:
                kg_item["value"]["class"] = embpred["object"][" ".join(kg_item["value"]["content"])]

            for triple in ["subject", "property", "value"]:
                for t_i in ["lemma_content", "content"]:
                    if isinstance(kg_item[triple][t_i], list):
                        kg_item[triple][t_i] = " ".join(kg_item[triple][t_i])
        return tkeir_doc

    def run(self, tkeir_doc):
        return self.infer(tkeir_doc)
