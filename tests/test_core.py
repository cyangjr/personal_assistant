from pathlib import Path

from assistant.actions import find_actions_for_product, get_action
from assistant.auth import is_allowed
from assistant.benefits import BenefitGraph
from assistant.db import Database
from assistant.llm import GroqAssistant
from assistant.memory import MemoryStore
from assistant.metrics import MetricsStore
from assistant.opportunities import OpportunityEngine
from assistant.wallet import WalletStore, parse_wallet_add_args, product_key


class FakeSearch:
    def __init__(self):
        self.calls = 0

    def search(self, query: str):
        self.calls += 1
        return [
            {
                "title": "Official benefits",
                "url": "https://www.chase.com/benefits",
                "content": "Includes travel credit and Ultimate Rewards points.",
            }
        ]


def test_allowlist():
    assert is_allowed(1, [1, 2])
    assert not is_allowed(3, [1, 2])


def test_memory_roundtrip(tmp_path: Path):
    store = MemoryStore(tmp_path / "test.db")
    store.add_message(42, "user", "hello")
    store.add_message(42, "model", "hi there")
    store.set_profile_note(42, "cards", "Chase Sapphire Preferred")

    history = store.get_recent_messages(42, 10)
    assert history == [
        {"role": "user", "content": "hello"},
        {"role": "model", "content": "hi there"},
    ]
    assert store.get_profile_notes(42)["cards"] == "Chase Sapphire Preferred"

    store.clear_messages(42)
    assert store.get_recent_messages(42, 10) == []
    assert store.delete_profile_note(42, "cards")
    assert store.get_profile_notes(42) == {}


def test_wallet_and_opportunities(tmp_path: Path):
    db = Database(tmp_path / "wallet.db")
    wallet = WalletStore(db)
    search = FakeSearch()
    benefits = BenefitGraph(db, search, max_age_days=7)
    engine = OpportunityEngine(db, wallet, benefits)

    item = wallet.add(
        chat_id=1,
        item_type="card",
        issuer="Chase",
        product_name="Sapphire Preferred",
        annual_fee=95,
        renewal_date="2099-01-01",
    )
    assert item.key == product_key("Chase", "Sapphire Preferred")
    assert "Sapphire Preferred" in wallet.format(1)

    created = engine.scan_chat(1)
    assert created
    assert engine.list_open(1)

    parsed = parse_wallet_add_args(
        ["Costco Executive", "fee=120", "renew=2099-12-01"]
    )
    assert parsed.resolve.status == "matched"
    assert parsed.resolve.product is not None
    assert parsed.resolve.product.issuer == "Costco"
    assert parsed.resolve.product.product_name == "Executive"
    assert parsed.annual_fee == 120

    ambiguous = parse_wallet_add_args(["sapphire"])
    assert ambiguous.resolve.status == "ambiguous"
    assert ambiguous.resolve.candidates
    assert len(ambiguous.resolve.candidates) == 2

    venture_x = parse_wallet_add_args(["Venture X"])
    assert venture_x.resolve.status == "matched"
    assert venture_x.resolve.product.product_name == "Venture X"


def test_benefit_cache(tmp_path: Path):
    db = Database(tmp_path / "benefits.db")
    search = FakeSearch()
    graph = BenefitGraph(db, search, max_age_days=7)
    doc1, hit1, calls1 = graph.ensure_product("Chase", "Sapphire Preferred")
    doc2, hit2, calls2 = graph.ensure_product("Chase", "Sapphire Preferred")
    assert doc1 is not None and doc2 is not None
    assert hit1 is False and calls1 == 1
    assert hit2 is True and calls2 == 0
    assert search.calls == 1


def test_actions_and_metrics(tmp_path: Path):
    assert get_action("chase_sapphire_preferred_travel_credit") is not None
    csp = find_actions_for_product("Chase Sapphire Preferred")
    csr = find_actions_for_product("Chase Sapphire Reserve")
    assert len(csp) == 1 and csp[0].key == "chase_sapphire_preferred_travel_credit"
    assert len(csr) == 1 and csr[0].key == "chase_sapphire_reserve_travel_credit"

    venture = find_actions_for_product("Capital One Venture")
    venture_x = find_actions_for_product("Capital One Venture X")
    assert len(venture) == 1 and venture[0].key == "capital_one_venture_miles"
    assert len(venture_x) == 1 and venture_x[0].key == "capital_one_venture_x_miles"

    db = Database(tmp_path / "metrics.db")
    metrics = MetricsStore(db)
    metrics.record(
        chat_id=1,
        kind="chat",
        latency_ms=120,
        prompt_tokens=100,
        completion_tokens=50,
        tavily_calls=1,
        cache_hit=False,
        model="llama-3.3-70b-versatile",
    )
    metrics.record(
        chat_id=1,
        kind="chat",
        latency_ms=80,
        prompt_tokens=40,
        completion_tokens=20,
        tavily_calls=0,
        cache_hit=True,
        model="llama-3.3-70b-versatile",
    )
    summary = metrics.summary(7)
    assert summary.events == 2
    assert summary.tavily_calls == 1
    assert summary.cache_hits == 1
    assert "Usage last" in metrics.format_summary(7)


def test_should_use_search(tmp_path: Path):
    db = Database(tmp_path / "llm.db")
    search = FakeSearch()
    graph = BenefitGraph(db, search)
    assistant = GroqAssistant(
        groq_api_key="unused",
        model="llama-3.3-70b-versatile",
        benefit_graph=graph,
        search=search,
    )
    assert assistant.should_use_search("What are my Costco Executive benefits?")
    assert assistant.should_use_search("Does Chase Sapphire have travel credit?")
    assert not assistant.should_use_search("What's a good pasta recipe?")
