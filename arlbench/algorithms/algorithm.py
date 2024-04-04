from abc import ABC, abstractmethod
from typing import Tuple, Optional, Any, Sequence, Union, Dict
import functools
import jax
import gymnax
import jax.numpy as jnp
from ConfigSpace import Configuration, ConfigurationSpace
from flashbax.buffers.prioritised_trajectory_buffer import PrioritisedTrajectoryBufferState
import gymnasium
import gym
import numpy as np
from arlbench.environments import Environment


class Algorithm(ABC):
    def __init__(
            self,
            hpo_config: Union[Configuration, Dict], 
            nas_config: Union[Configuration, Dict], 
            env_options: Dict, 
            env: Environment, 
            track_metrics=False,
            track_trajectories=False
        ) -> None:
        super().__init__()

        self.hpo_config = hpo_config
        self.nas_config = nas_config
        self.env_options = env_options
        self.env = env
        self.track_metrics = track_metrics
        self.track_trajectories = track_trajectories

    @property
    def action_type(self) -> Tuple[Sequence[int], bool]:
        action_space = self.env.action_space

        if isinstance(
            action_space, gymnax.environments.spaces.Discrete
        ) or isinstance(
            action_space, gym.spaces.Discrete
        ) or isinstance(
            action_space, gymnasium.spaces.Discrete
        ):
            action_size = action_space.n
            discrete = True
        elif isinstance(
            action_space, gymnax.environments.spaces.Box
        ) or isinstance(
            action_space, gym.spaces.Box
        ) or isinstance(
            action_space, gymnasium.spaces.Box
        ):
            action_size = action_space.shape[0]
            discrete = False
        else:
            raise NotImplementedError(
                f"Only Discrete and Box action spaces are supported, got {self.env.action_space}."
            )

        return action_size, discrete
    
    @staticmethod
    @abstractmethod
    def get_hpo_config_space(seed=None) -> ConfigurationSpace:
        pass

    @staticmethod
    @abstractmethod
    def get_default_hpo_config() -> Configuration:
        pass

    @staticmethod
    @abstractmethod
    def get_nas_config_space(seed=None) -> ConfigurationSpace:
        pass

    @staticmethod
    @abstractmethod
    def get_default_nas_config() -> Configuration:
        pass
    
    @abstractmethod
    def init(self, rng) -> tuple[Any, Any]:
        pass

    @abstractmethod
    def train(self, runner_state: Any, buffer_state: Any) -> Tuple[tuple[Any, PrioritisedTrajectoryBufferState], Optional[Tuple]]:
        pass

    @abstractmethod 
    @functools.partial(jax.jit, static_argnums=0)
    def predict(self, runner_state, obsv, rng = None) -> Any:
        pass

    @functools.partial(jax.jit, static_argnums=0)
    def _env_episode(self, runner_state, _):
        rng, _rng = jax.random.split(runner_state.rng)
        _rng, reset_rng = jax.random.split(_rng)

        env_state, obs = self.env.reset(reset_rng) 
        initial_state = (
            env_state,
            obs,
            jnp.full((self.env.n_envs,), 0.), 
            jnp.full((self.env.n_envs,), False),
            _rng,
            runner_state
        )

        def cond_fn(state):
            _, _, _, done, _, _ = state
            return jnp.logical_not(jnp.all(done))

        def body_fn(state):
            env_state, obs, reward, done, rng, runner_state = state

            # SELECT ACTION
            rng, action_rng = jax.random.split(rng)
            action = self.predict(runner_state, obs, action_rng)

            # STEP ENV
            rng, step_rng = jax.random.split(rng)
            env_state, (obs, reward_, done_, _) = self.env.step(env_state, action, step_rng)

            # Count rewards only for envs that are not already done
            reward += reward_ * ~done
            
            done = jnp.logical_or(done, done_)

            return env_state, obs, reward, done, rng, runner_state

        final_state = jax.lax.while_loop(cond_fn, body_fn, initial_state)
        _, _, reward, _, _, _ = final_state

        return runner_state, reward  

    def eval(self, runner_state, num_eval_episodes):
        # Number of parallel evaluations, each with n_envs environments
        if num_eval_episodes > self.env.n_envs:
            n_evals = int(jnp.ceil(num_eval_episodes / self.env.n_envs))
        else:
            n_evals = 1

        rewards = []

        _, rewards = jax.lax.scan(
            self._env_episode, runner_state, None, n_evals
        )

        return jnp.concat(rewards)[:num_eval_episodes]

    