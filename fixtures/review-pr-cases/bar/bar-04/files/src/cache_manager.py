"""Cache Manager module handling partition lifecycle and eviction."""
import yaml

class CacheManager:
    def __init__(self, config_path: str):
        with open(config_path, "r") as f:
            self.config = yaml.safe_load(f)
        self.pinned = set(self.config.get("pinned_namespaces", []))
        self.policy = self.config.get("eviction_policy", "lru")
        self.target_memory = self.config.get("target_memory_mb", 4096)

    def is_evictable(self, namespace: str) -> bool:
        return namespace not in self.pinned

    def run(self):
        print(f"Initialized CacheManager with policy={self.policy}")
