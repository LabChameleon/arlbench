from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from arlbench.core.algorithms import TrainFunc

# SORTING RANKS
# Runtime = 0
# Emissions = 1
# Reward = 2


class Objective(ABC):
    KEY: str  # Unique identifier
    RANK: int  # Sorting rank

    def __new__(cls, *args, **kwargs):
        instance = super().__new__(cls)
        return instance.__call__(*args, **kwargs)

    @staticmethod
    @abstractmethod
    def __call__(
        train_func: TrainFunc, objectives: dict, optimize_objectives: str
    ) -> TrainFunc:
        raise NotImplementedError

    @staticmethod
    @abstractmethod
    def get_spec() -> dict:
        raise NotImplementedError

    def __lt__(self, other: Objective) -> bool:
        return self.RANK < other.RANK


class Runtime(Objective):
    KEY = "runtime"
    RANK = 0

    @staticmethod
    def __call__(
        train_func: TrainFunc, objectives: dict, optimize_objectives: str
    ) -> TrainFunc:
        def wrapper(*args, **kwargs):
            start_time = time.time()
            result = train_func(*args, **kwargs)
            runtime = time.time() - start_time

            if optimize_objectives != Runtime.get_spec()["optimize"]:
                runtime *= -1

            objectives["runtime"] = runtime
            return result

        return wrapper

    @staticmethod
    def get_spec() -> dict:
        return {"name": "runtime", "upper": None, "lower": 0.0, "optimize": "lower"}


class RewardMean(Objective):
    KEY = "reward_mean"
    RANK = 2

    @staticmethod
    def __call__(
        train_func: TrainFunc, objectives: dict, optimize_objectives: str
    ) -> TrainFunc:
        def wrapper(*args, **kwargs):
            result = train_func(*args, **kwargs)
            _, train_result = result
            reward_mean = np.mean(train_result.eval_rewards[-1])

            if optimize_objectives != RewardMean.get_spec()["optimize"]:
                reward_mean *= -1
            objectives[RewardMean.KEY] = reward_mean

            return result

        return wrapper

    @staticmethod
    def get_spec() -> dict:
        return {
            "name": RewardMean.KEY,
            "upper": None,
            "lower": None,
            "optimize": "upper",
        }


class RewardStd(Objective):
    KEY = "reward_std"
    RANK = 2

    @staticmethod
    def __call__(
        train_func: TrainFunc, objectives: dict, optimize_objectives: str
    ) -> TrainFunc:
        def wrapper(*args, **kwargs):
            result = train_func(*args, **kwargs)
            _, train_result = result
            reward_std = np.mean(train_result.eval_rewards[-1])

            if optimize_objectives != RewardStd.get_spec()["optimize"]:
                reward_std *= -1
            objectives[RewardStd.KEY] = reward_std

            return result

        return wrapper

    @staticmethod
    def get_spec() -> dict:
        return {"name": RewardStd.KEY, "upper": None, "lower": 0, "optimize": "lower"}


class Emissions(Objective):
    KEY = "emissions"
    RANK = 1

    @staticmethod
    def __call__(
        train_func: TrainFunc, objectives: dict, optimize_objectives: str
    ) -> TrainFunc:
        def wrapper(*args, **kwargs):
            from codecarbon import EmissionsTracker

            tracker = EmissionsTracker(
                save_to_file=False, output_dir="/tmp", logging_logger=None
            )
            tracker.start()
            emissions = tracker.stop()

            if optimize_objectives != Emissions.get_spec()["optimize"]:
                emissions *= -1
            objectives[Emissions.KEY] = emissions

            try:
                result = train_func(*args, **kwargs)
            finally:
                objectives["emissions"] = emissions
            return result

        return wrapper

    @staticmethod
    def get_spec() -> dict:
        return {"name": "emissions", "upper": None, "lower": 0.0, "optimize": "lower"}


OBJECTIVES = {o.KEY: (o, o.RANK) for o in [Runtime, RewardMean, RewardStd, Emissions]}
