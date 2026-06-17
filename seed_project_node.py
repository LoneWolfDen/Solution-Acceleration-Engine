import asyncio
import aiosqlite
from contexta.db.repositories import create_project, write_node
from contexta.models.payloads import ReviewNodePayload, IssueFinding
from contexta.models.citations import SourceCitation
from contexta.models.enums import ConfidenceEnum, MitigationRoutingEnum, CitationTypeEnum

async def seed_test_node():
    async with aiosqlite.connect("./contexta.db") as conn:
        conn.row_factory = aiosqlite.Row
        
        proj = await create_project(conn, "Alpha-Project", ["gen-ai"])
        
        dimensions = [
            'Intent', 'Scope', 'Ownership', 'Delivery', 'Timeline', 
            'Architecture', 'NFR', 'Resource', 'Risk', 'Commercial', 
            'Language', 'Consistency'
        ]
        
        findings = [
            IssueFinding(
                dimension=dim,
                confidence=ConfidenceEnum.GREEN,
                summary=f"Summary for {dim}",
                detail=f"Detailed analysis for {dim}",
                citations=[SourceCitation(
                    source="SOW", 
                    reference="Slide 1",
                    file_path="docs/sow.pdf",
                    line_start=10,
                    line_end=12,
                    citation_type=CitationTypeEnum.DIRECT_REFERENCE,
                    excerpt="Sample requirement text."
                )],
                mitigation_routing=MitigationRoutingEnum.RISK_REGISTER
            ) for dim in dimensions
        ]
        
        # 4. Create the valid payload with correct Enum types
        payload = ReviewNodePayload(
            dimension='Intent',  # Added missing root-level dimension
            findings=findings,
            overall_confidence=ConfidenceEnum.GREEN, # Updated to Enum
            raw_llm_response="Mock synthesis"
        )
        
        # 5. Write the node
        await write_node(
            conn,
            project_id=proj.id,
            parent_id=None,
            layer_type="exploration",
            node_name="Test-Node-001",
            payload=payload,
            metadata={"test": "data"}
        )
        print("Successfully seeded node with 12 valid IssueFindings.")

if __name__ == "__main__":
    asyncio.run(seed_test_node())
