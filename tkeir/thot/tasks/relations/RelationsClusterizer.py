# -*- coding: utf-8 -*-
"""Relation clustering
Author : Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""
import traceback
from sklearn.cluster import MiniBatchKMeans
import numpy as np
from numpy import linalg as LA
from copy import deepcopy
from thot.tasks.relations.RelationClusterizerConfiguration import RelationClusterizerConfiguration
from thot.core.ThotLogger import ThotLogger
import pickle


class RelationsClusterizer:

    IDX_SUBJECT = 0
    IDX_PROPERTY = 1
    IDX_OBJECT = 2
    IDX_KW = 3
    name2index = {"subject": 0, "relation": 1, "object": 2, "keyword": 3}

    def __init__(self, config: RelationClusterizerConfiguration = None, model_file_handler: str = None):
        if (config is None) and (model_file_handler is None):
            raise ValueError("Configuration or model is mandatory")
        self._means = []
        if config:
            self.config = config
            for i in [
                RelationsClusterizer.IDX_SUBJECT,
                RelationsClusterizer.IDX_PROPERTY,
                RelationsClusterizer.IDX_OBJECT,
                RelationsClusterizer.IDX_KW,
            ]:
                self._means.append(
                    MiniBatchKMeans(
                        n_clusters=config.configuration["cluster"]["number-of-classes"],
                        random_state=config.configuration["cluster"]["number-of-iterations"],
                        batch_size=config.configuration["cluster"]["batch-size"],
                        n_init=10,
                    )
                )
        elif model_file_handler:
            self.load(model_file_handler)
        self._last_center = [None, None, None, None]
        self._total_vector = [0, 0, 0, 0]

    def add(self, all_data: list = None, all_weights: list = None, vtypes: list = None):
        if all_data is not None:
            data = [[], [], [], []]
            weights = [[], [], [], []]
            for vi in range(len(all_data)):
                data[RelationsClusterizer.name2index[vtypes[vi]]].append(all_data[vi])
                weights[RelationsClusterizer.name2index[vtypes[vi]]].append(all_weights[vi])

            norm = [-1, -1, -1, -1]
            for i in [
                RelationsClusterizer.IDX_SUBJECT,
                RelationsClusterizer.IDX_PROPERTY,
                RelationsClusterizer.IDX_OBJECT,
                RelationsClusterizer.IDX_KW,
            ]:
                try:
                    self._total_vector[i] = self._total_vector[i] + len(data[i])
                    self._means[i].partial_fit(np.array(data[i]), sample_weight=weights[i])
                    copy_centers = deepcopy(self._means[i].cluster_centers_)
                    if self._last_center[i] is not None:
                        norm[i] = LA.norm(self._last_center[i] - copy_centers)
                    self._last_center[i] = copy_centers
                except Exception as e:
                    ThotLogger.error("Kmeans error:" + str(traceback.format_exc()))
        return (norm, self._total_vector)

    def predict(self, data: list = None, index=0):
        if data is not None:
            return self._means[index].predict(data).tolist()
        return []

    def save(self, handler_f):
        pickle.dump(self._means, handler_f)

    def load(self, handler_f):
        self._means = pickle.load(handler_f)
