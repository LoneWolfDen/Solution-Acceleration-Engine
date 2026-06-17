import asyncio
import aiosqlite
from contexta.config import ContextaConfig
from contexta.pipeline.arbitrator import ArbitratorEngine
from contexta.llm.prompts import PromptBuilder
from contexta.db.repositories import list_all_nodes, get_active_blueprint
from contexta.models.payloads import ReviewNodePayload, IssueFinding
from contexta.models.enums import ConfidenceEnum, MitigationRoutingEnum, CitationTypeEnum

class ConfigWrapper:
    def __init__(self, config: ContextaConfig):
        self._config = config
        self.model = config.llm_backend 
        self.api_key = config.llm_api_key
        self.base_url = config.llm_base_url
    
    def __getattr__(self, name):
        return getattr(self._config, name)

async def inspect_arbitrator():
    config = ContextaConfig()
    wrapped_config = ConfigWrapper(config)
    
    async with aiosqlite.connect("./contexta.db") as conn:
        conn.row_factory = aiosqlite.Row
        
        blueprint = await get_active_blueprint(conn)
        builder = PromptBuilder(blueprint=blueprint, schema_json="{}")
        
        # 1. Create a minimal valid payload with 12 tiny findings
        # This keeps the token count low while satisfying the engine's count check
        findings = [
            IssueFinding(
                dimension='Intent',
                confidence=ConfidenceEnum.GREEN,
                summary=".",
                detail=".",
                citations=[],
                mitigation_routing=MitigationRoutingEnum.RISK_REGISTER
            ) for _ in range(12)
        ]
        
        payload = ReviewNodePayload(
            dimension='Intent',
            findings=findings,
            overall_confidence=ConfidenceEnum.GREEN,
            raw_llm_response="Minimal"
        )
        
        # The engine likely expects a list of 12 separate payload objects
        payloads = [payload] * 12
        
        # 2. Run Arbitrator
        arbitrator = ArbitratorEngine(wrapped_config, builder)
        print("Executing Arbitrator synthesis with 12 minimal payloads...")
        
        try:
            result = await arbitrator.run(payloads)
            print("\n--- ARBITRATOR RESULT ---")
            print(f"Contradictions detected: {len(result.contradictions)}")
            print("\nRaw LLM Response:\n", result.raw_llm_response)
        except Exception as e:
            print(f"Synthesis failed: {e}")

if __name__ == "__main__":
    asyncio.run(inspect_arbitrator())
