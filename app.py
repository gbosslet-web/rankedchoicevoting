from __future__ import annotations

import re
from urllib.parse import quote

import pandas as pd
import plotly.express as px
import streamlit as st
try:
    from streamlit_autorefresh import st_autorefresh
except ImportError:
    st_autorefresh = None
try:
    from streamlit_sortables import sort_items
except ImportError:
    sort_items = None

import db
from rcv import tabulate_stv


st.set_page_config(page_title="Board RCV", page_icon="✓", layout="wide")


def inject_css() -> None:
    st.markdown(
        """
        <style>
        :root {
            --brand: #4f46e5;
            --ink: #111827;
            --muted: #6b7280;
            --line: #e5e7eb;
            --soft: #f9fafb;
        }
        .block-container {
            padding-top: 2rem;
            padding-bottom: 3rem;
            max-width: 1180px;
        }
        [data-testid="stSidebar"] {
            background: #f9fafb;
            border-right: 1px solid #eef0f4;
        }
        h1, h2, h3 {
            letter-spacing: 0;
            color: var(--ink);
        }
        p, label, span {
            color: var(--ink);
        }
        div[data-testid="stMetric"] {
            background: #ffffff;
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 1rem;
            box-shadow: 0 8px 24px rgba(17, 24, 39, 0.04);
        }
        div[data-testid="stForm"], div[data-testid="stVerticalBlockBorderWrapper"] {
            border-radius: 8px;
            border-color: var(--line);
        }
        .stButton > button, .stDownloadButton > button {
            border-radius: 8px;
            border: 1px solid #4338ca;
            background: var(--brand);
            color: white;
            font-weight: 650;
            min-height: 2.75rem;
        }
        .stButton > button:hover, .stDownloadButton > button:hover {
            border-color: #3730a3;
            background: #4338ca;
            color: white;
        }
        .secondary button {
            background: white !important;
            color: var(--ink) !important;
            border-color: var(--line) !important;
        }
        .hero {
            padding: 1.25rem 0 1rem;
            border-bottom: 1px solid #eef0f4;
            margin-bottom: 1.25rem;
        }
        .eyebrow {
            color: var(--brand);
            font-size: .8rem;
            font-weight: 750;
            letter-spacing: .08em;
            text-transform: uppercase;
            margin-bottom: .35rem;
        }
        .muted {
            color: var(--muted);
        }
        .callout {
            background: var(--soft);
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 1rem 1.15rem;
        }
        .winner-pill {
            display: inline-block;
            padding: .4rem .65rem;
            border-radius: 999px;
            margin: .2rem .25rem .2rem 0;
            background: #ecfdf5;
            color: #065f46;
            border: 1px solid #a7f3d0;
            font-weight: 700;
        }
        .rank-preview {
            display: flex;
            align-items: center;
            gap: .65rem;
            padding: .75rem .9rem;
            border: 1px solid var(--line);
            border-radius: 8px;
            background: #ffffff;
            margin-bottom: .5rem;
        }
        .rank-number {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 2rem;
            height: 2rem;
            border-radius: 999px;
            background: #eef2ff;
            color: var(--brand);
            font-weight: 800;
            flex: 0 0 auto;
        }
        .rank-name {
            font-weight: 700;
        }
        .results-summary {
            display: grid;
            grid-template-columns: minmax(260px, .9fr) minmax(320px, 1.1fr);
            gap: 1rem;
            margin: 1rem 0 1.25rem;
        }
        @media (max-width: 820px) {
            .results-summary {
                grid-template-columns: 1fr;
            }
        }
        .summary-panel {
            border: 1px solid var(--line);
            border-radius: 8px;
            background: #ffffff;
            padding: 1rem;
            box-shadow: 0 8px 24px rgba(17, 24, 39, 0.04);
        }
        .summary-panel h3 {
            font-size: 1rem;
            margin: 0 0 .75rem;
        }
        .standing-row {
            display: grid;
            grid-template-columns: 2.2rem minmax(0, 1fr) auto;
            align-items: center;
            gap: .65rem;
            padding: .65rem 0;
            border-top: 1px solid #f0f2f5;
        }
        .standing-row:first-of-type {
            border-top: 0;
        }
        .standing-rank {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 1.8rem;
            height: 1.8rem;
            border-radius: 999px;
            background: #eef2ff;
            color: var(--brand);
            font-weight: 800;
        }
        .standing-name {
            font-weight: 750;
        }
        .standing-status {
            border-radius: 999px;
            border: 1px solid #e5e7eb;
            color: #374151;
            font-size: .78rem;
            font-weight: 750;
            padding: .22rem .5rem;
            white-space: nowrap;
        }
        .standing-status.elected {
            background: #ecfdf5;
            border-color: #a7f3d0;
            color: #065f46;
        }
        .standing-status.eliminated {
            background: #f9fafb;
            color: #6b7280;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def current_secret(name: str) -> str:
    try:
        return str(st.secrets.get(name, "")).strip()
    except Exception:
        return ""


def app_base_url() -> str:
    configured = current_secret("APP_BASE_URL")
    if configured:
        return configured.rstrip("/")
    return "https://your-app.streamlit.app"


def parse_candidates(raw: str) -> list[dict[str, str]]:
    candidates = []
    for line in raw.splitlines():
        value = line.strip()
        if not value:
            continue
        if "|" in value:
            name, bio = [part.strip() for part in value.split("|", 1)]
        else:
            name, bio = value, ""
        if name:
            candidates.append({"name": name, "bio": bio})
    return candidates


def parse_voter_labels(raw: str) -> list[str]:
    labels = []
    seen = set()
    for line in raw.splitlines():
        label = re.sub(r"\s+", " ", line.strip())
        if not label:
            continue
        dedupe_key = label.lower()
        if dedupe_key in seen:
            continue
        labels.append(label)
        seen.add(dedupe_key)
    return labels


def candidate_sortable_styles() -> str:
    return """
    .sortable-component.vertical {
        gap: 10px;
        padding: 2px;
    }
    .sortable-container {
        border: 0;
        background: transparent;
        padding: 0;
    }
    .sortable-container-header {
        display: none;
    }
    .sortable-container-body {
        display: flex;
        flex-direction: column;
        gap: 10px;
    }
    .sortable-item {
        position: relative;
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        background: #ffffff;
        box-shadow: 0 8px 22px rgba(17, 24, 39, 0.06);
        color: #111827;
        cursor: grab;
        font-size: 17px;
        font-weight: 700;
        min-height: 58px;
        padding: 16px 18px 16px 52px;
        transition: border-color 140ms ease, box-shadow 140ms ease, transform 140ms ease;
    }
    .sortable-item::before {
        content: "⋮⋮";
        position: absolute;
        left: 18px;
        top: 50%;
        transform: translateY(-50%);
        color: #9ca3af;
        font-weight: 900;
        letter-spacing: -2px;
    }
    .sortable-item:hover {
        border-color: #c7d2fe;
        box-shadow: 0 12px 28px rgba(79, 70, 229, 0.12);
        transform: translateY(-1px);
    }
    .sortable-item:active {
        cursor: grabbing;
    }
    """


def render_unranked_helper() -> None:
    st.markdown(
        """
        <div class="callout">
            <strong>Leaving someone unranked:</strong> check their name below. They will be removed from
            the submitted ballot. Drag the remaining placards to set your ranking.
        </div>
        """,
        unsafe_allow_html=True,
    )


def unique_candidate_labels(candidates: list[dict]) -> tuple[list[str], dict[str, str]]:
    seen: dict[str, int] = {}
    labels = []
    label_to_id = {}
    for candidate in candidates:
        name = candidate["name"]
        seen[name] = seen.get(name, 0) + 1
        label = name if seen[name] == 1 else f"{name} ({seen[name]})"
        labels.append(label)
        label_to_id[label] = candidate["id"]
    return labels, label_to_id


def friendly_db_error() -> None:
    render_setup_help(
        "The app cannot reach Supabase yet. You can still log into admin, "
        "but elections and ballots need a connected Supabase project."
    )


def supabase_secrets_ready() -> bool:
    url = current_secret("SUPABASE_URL")
    key = current_secret("SUPABASE_KEY")
    return bool(url and key and "your-supabase-project" not in url and "your-anon-public-key" not in key)


def render_setup_help(message: str | None = None) -> None:
    if message:
        st.warning(message)

    st.markdown("### Finish Supabase Setup")
    st.markdown(
        """
        The app is already built locally. The only part I cannot do from here is create or access your Supabase project,
        because those credentials live in your browser account.

        1. Open your Supabase project.
        2. Go to **SQL Editor** and run `supabase/migration.sql`.
        3. Go to **Project Settings -> API**.
        4. Copy **Project URL** into `SUPABASE_URL`.
        5. Copy the **anon public** key into `SUPABASE_KEY`.
        6. Refresh this Streamlit page.
        """
    )
    st.code(
        '''SUPABASE_URL = "https://your-project.supabase.co"
SUPABASE_KEY = "your-anon-public-key"
ADMIN_PASSWORD = "admin"
APP_BASE_URL = "http://localhost:8501"''',
        language="toml",
    )
    st.info("For Streamlit Cloud, paste the same values into the app's Secrets settings and change `ADMIN_PASSWORD` to something private.")


def fetch_results(election_id: str, seats_available: int) -> dict:
    candidates = db.fetch_candidates(election_id)
    ballots = db.fetch_ballots(election_id)
    candidate_map = {row["id"]: row["name"] for row in candidates}
    rankings = [row["ranking"] for row in ballots]
    return tabulate_stv(rankings, candidate_map, seats_available)


def seat_boundary_ties(results: dict, seats_available: int) -> list[dict]:
    standings = result_standings(results)
    seats = int(seats_available)
    if seats < 1 or len(standings) <= seats:
        return []

    cutoff = standings[seats - 1]
    next_candidate = standings[seats]
    cutoff_votes = cutoff.get("votes")
    next_votes = next_candidate.get("votes")
    if cutoff_votes is None or next_votes is None:
        return []

    if abs(float(cutoff_votes) - float(next_votes)) > 1e-9:
        return []

    tied_names = [
        row["candidate"]
        for row in standings
        if row.get("votes") is not None and abs(float(row["votes"]) - float(cutoff_votes)) <= 1e-9
    ]
    return [
        {
            "round": "Current",
            "type": f"Tie at final elected position ({seats})",
            "candidates": sorted(tied_names, key=str.lower),
            "resolution": (
                f"The current cutoff between rank {seats} and rank {seats + 1} is tied at "
                f"{float(cutoff_votes):g} votes. Review your tie-breaking rule before certifying."
            ),
        }
    ]


def render_tie_warnings(results: dict, seats_available: int) -> None:
    ties = seat_boundary_ties(results, seats_available)
    if not ties:
        st.success("No tie detected at the final elected position.")
        return

    st.warning(
        "Tie detected at the final elected position. Pause before certifying results and apply your board's tie-breaking rule."
    )
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Round": tie["round"],
                    "Tie type": tie["type"],
                    "Candidates": ", ".join(tie["candidates"]),
                    "App resolution": tie["resolution"],
                }
                for tie in ties
            ]
        ),
        hide_index=True,
        use_container_width=True,
    )


def protocol_audit(election: dict, results: dict) -> pd.DataFrame:
    candidates = db.fetch_candidates(election["id"])
    voters = db.fetch_voters(election["id"])
    ballots = db.fetch_ballots(election["id"])
    candidate_ids = {candidate["id"] for candidate in candidates}
    expected_quota = results["total_ballots"] // (int(election["seats_available"]) + 1) + 1 if results["total_ballots"] else 0

    invalid_references = 0
    duplicate_rankings = 0
    empty_rankings = 0
    for ballot in ballots:
        ranking = ballot.get("ranking") or []
        if not ranking:
            empty_rankings += 1
        if len(ranking) != len(set(ranking)):
            duplicate_rankings += 1
        invalid_references += sum(1 for candidate_id in ranking if candidate_id not in candidate_ids)

    voted_count = sum(1 for voter in voters if voter.get("has_voted"))
    winner_ids = [winner["candidate_id"] for winner in results.get("winners", [])]
    ties = seat_boundary_ties(results, int(election["seats_available"]))
    tie_note = "No tie detected at the final elected position."
    tie_status = "Pass"
    if ties:
        tie_status = "Review"
        tie_note = "Tie detected at the final elected position. Apply your board's tie-breaking rule before certifying."
    if len(candidates) <= int(election["seats_available"]):
        tie_note = "Not applicable unless more candidates are added than available seats."
        tie_status = "Pass"

    checks = [
        {
            "Check": "Counting method",
            "Status": "Pass",
            "Detail": "Single-seat elections use instant-runoff behavior; multi-seat elections use STV with a Droop quota.",
        },
        {
            "Check": "Droop quota",
            "Status": "Pass" if expected_quota == results["quota"] else "Review",
            "Detail": f"Expected {expected_quota}; app calculated {results['quota']}.",
        },
        {
            "Check": "Ballot count",
            "Status": "Pass" if len(ballots) == results["total_ballots"] else "Review",
            "Detail": f"{len(ballots)} stored ballots; {results['total_ballots']} counted ballots.",
        },
        {
            "Check": "Single-use links",
            "Status": "Pass" if voted_count == len(ballots) else "Review",
            "Detail": f"{voted_count} voters marked voted; {len(ballots)} ballots stored.",
        },
        {
            "Check": "Ballot rankings",
            "Status": "Pass" if not empty_rankings and not duplicate_rankings and not invalid_references else "Review",
            "Detail": f"{empty_rankings} empty, {duplicate_rankings} duplicate-ranking, {invalid_references} invalid-candidate issues.",
        },
        {
            "Check": "Winners",
            "Status": "Pass" if len(winner_ids) <= int(election["seats_available"]) and len(winner_ids) == len(set(winner_ids)) else "Review",
            "Detail": f"{len(winner_ids)} elected for {election['seats_available']} available seat(s).",
        },
        {
            "Check": "Tie protocol",
            "Status": tie_status,
            "Detail": tie_note,
        },
    ]
    return pd.DataFrame(checks)


def result_standings(results: dict) -> list[dict]:
    if not results.get("rounds"):
        return []

    latest_totals = {}
    for round_data in results["rounds"]:
        for row in round_data["totals"]:
            latest_totals[row["candidate_id"]] = row

    winners = results.get("winners", [])
    winner_ids = {winner["candidate_id"] for winner in winners}

    standings = []
    for winner in winners:
        latest = latest_totals.get(winner["candidate_id"], {})
        standings.append(
            {
                "candidate": winner["candidate"],
                "votes": latest.get("votes"),
                "status": "elected",
            }
        )

    remaining = [
        row
        for row in latest_totals.values()
        if row["candidate_id"] not in winner_ids
    ]
    remaining.sort(
        key=lambda row: (
            0 if row["status"] == "continuing" else 1,
            -float(row.get("votes", 0)),
            row["candidate"].lower(),
        )
    )
    standings.extend(
        {
            "candidate": row["candidate"],
            "votes": row.get("votes"),
            "status": row["status"],
        }
        for row in remaining
    )
    return standings


def render_results_summary(results: dict, seats_available: int) -> None:
    winners = results.get("winners", [])
    standings = result_standings(results)

    st.markdown("### Election Snapshot")

    if not results["total_ballots"]:
        st.info("No ballots have been cast yet. Elected candidates and rank order will appear here as votes come in.")
        return

    winner_column, standing_column = st.columns([0.9, 1.1])
    with winner_column:
        st.markdown(f"#### Elected candidates ({len(winners)} of {seats_available})")
        if winners:
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Seat": index,
                            "Candidate": winner["candidate"],
                            "Status": "Elected",
                        }
                        for index, winner in enumerate(winners, start=1)
                    ]
                ),
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.info("No candidate has reached the election threshold yet.")

    with standing_column:
        st.markdown("#### Current rank order")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Rank": index,
                        "Candidate": row["candidate"],
                        "Latest votes": row.get("votes", ""),
                        "Status": row["status"].title(),
                    }
                    for index, row in enumerate(standings, start=1)
                ]
            ),
            hide_index=True,
            use_container_width=True,
        )


def render_results(election: dict) -> None:
    results = fetch_results(election["id"], election["seats_available"])
    st.subheader("Live RCV Results")

    metric_cols = st.columns(3)
    metric_cols[0].metric("Ballots Cast", results["total_ballots"])
    metric_cols[1].metric("Seats", election["seats_available"])
    metric_cols[2].metric("Droop Quota", results["quota"])

    render_tie_warnings(results, election["seats_available"])
    render_results_summary(results, election["seats_available"])

    rows = []
    for round_data in results["rounds"]:
        for total in round_data["totals"]:
            rows.append(
                {
                    "Round": round_data["round"],
                    "Candidate": total["candidate"],
                    "Votes": total["votes"],
                    "Status": total["status"],
                }
            )

    if rows:
        frame = pd.DataFrame(rows)
        fig = px.bar(
            frame,
            x="Candidate",
            y="Votes",
            color="Status",
            animation_frame="Round",
            barmode="group",
            color_discrete_map={
                "elected": "#10b981",
                "continuing": "#4f46e5",
                "eliminated": "#9ca3af",
                "inactive": "#d1d5db",
            },
        )
        fig.update_layout(
            margin=dict(l=10, r=10, t=20, b=10),
            plot_bgcolor="white",
            paper_bgcolor="white",
            font=dict(color="#111827"),
            legend_title_text="",
        )
        st.plotly_chart(fig, use_container_width=True)

        with st.expander("Round-by-round detail", expanded=True):
            for round_data in results["rounds"]:
                st.markdown(f"**Round {round_data['round']}** · {round_data['action']}")
                st.dataframe(pd.DataFrame(round_data["totals"]), hide_index=True, use_container_width=True)

    with st.expander("Protocol audit", expanded=False):
        st.dataframe(protocol_audit(election, results), hide_index=True, use_container_width=True)
        st.caption(
            "Tie protocol is only flagged when a tie affects the final elected position, such as rank 5 vs rank 6 for five seats."
        )


def render_thank_you(election: dict) -> None:
    st.markdown('<div class="hero"><div class="eyebrow">Ballot submitted</div><h1>Thank you for voting.</h1></div>', unsafe_allow_html=True)
    if election.get("results_visible"):
        render_results(election)
    else:
        st.markdown('<div class="callout">Results will be shared by the administrator shortly.</div>', unsafe_allow_html=True)


def render_voter(token: str) -> None:
    try:
        voter = db.fetch_voter_by_token(token)
        if not voter or voter["has_voted"]:
            st.error("This voting link is invalid or has already been used.")
            return

        election = db.fetch_election(voter["election_id"])
        if not election or election["status"] != "active":
            st.error("This election is not currently accepting ballots.")
            return

        candidates = db.fetch_candidates(election["id"])
    except Exception:
        friendly_db_error()
        return

    if st.session_state.get("submitted_token") == token:
        render_thank_you(election)
        return

    st.markdown(
        f"""
        <div class="hero">
            <div class="eyebrow">Ranked-choice ballot</div>
            <h1>{election["title"]}</h1>
            <p class="muted">Rank as many candidates as you wish. Each candidate can be ranked once.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not candidates:
        st.info("No candidates are available for this election yet.")
        return

    labels, label_to_id = unique_candidate_labels(candidates)

    if sort_items is not None:
        st.markdown("#### Drag candidates into your preferred order")
        st.caption("Top placard is your first choice.")
        render_unranked_helper()

        st.markdown("##### Do not rank")
        excluded = []
        checkbox_columns = st.columns(2)
        for index, label in enumerate(labels):
            with checkbox_columns[index % 2]:
                if st.checkbox(label, key=f"exclude-{election['id']}-{voter['id']}-{label}"):
                    excluded.append(label)

        ranked_labels = [label for label in labels if label not in excluded]
        if excluded:
            st.caption(f"Not ranked: {', '.join(excluded)}")

        if not ranked_labels:
            st.warning("Please leave at least one candidate ranked before submitting.")
            selected = []
        else:
            st.markdown("##### Ranked choices")
            selected = sort_items(
                ranked_labels,
                direction="vertical",
                custom_style=candidate_sortable_styles(),
                key=f"candidate-sort-{election['id']}-{voter['id']}-{'-'.join(ranked_labels)}",
            )
    else:
        st.warning("Drag-and-drop ranking is not available, so this ballot is using the fallback ranking controls.")
        available_names = list(label_to_id.keys())
        selected: list[str] = []
        for rank in range(1, len(candidates) + 1):
            choices = ["No selection"] + [name for name in available_names if name not in selected]
            choice = st.selectbox(f"Rank {rank}", choices, key=f"rank_{rank}")
            if choice != "No selection":
                selected.append(choice)

    st.markdown("#### Your ballot")
    for index, label in enumerate(selected, start=1):
        st.markdown(
            f"""
            <div class="rank-preview">
                <span class="rank-number">{index}</span>
                <span class="rank-name">{label}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    confirm = st.checkbox("I confirm this ranking is final and my link will be marked as used.")
    submitted = st.button("Submit Ballot", type="primary")

    if submitted:
        if not selected:
            st.warning("Please rank at least one candidate before submitting.")
            return
        if not confirm:
            st.warning("Please confirm your ballot before submitting.")
            return

        ranking = [label_to_id[name] for name in selected]
        try:
            db.submit_ballot(voter["id"], election["id"], ranking)
            st.session_state["submitted_token"] = token
            st.rerun()
        except Exception:
            st.error("We could not submit your ballot. Please refresh and try again.")


def render_link_table(voters: list[dict]) -> None:
    if not voters:
        st.info("No voter links have been generated yet.")
        return

    rows = []
    for voter in voters:
        token = voter["token"]
        link = f"{app_base_url()}/?token={quote(token)}"
        rows.append(
            {
                "Name": voter["email"],
                "Voting Link": link,
                "Voted": "Yes" if voter["has_voted"] else "No",
            }
        )
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    markdown_links = "\n".join(f"- [{row['Name']}]({row['Voting Link']})" for row in rows)
    html_links = "\n".join(f'<p><a href="{row["Voting Link"]}">{row["Name"]}</a></p>' for row in rows)

    st.markdown("##### Google Docs link list")
    st.caption("Copy the Markdown list below into a Google Doc. Each name points to that person’s unique voting link.")
    st.text_area(
        "Copy/paste hyperlink list",
        markdown_links,
        height=min(320, max(140, 28 * len(rows))),
        label_visibility="collapsed",
    )
    st.download_button(
        "Download Google Docs links as HTML",
        html_links,
        file_name="voting_links.html",
        mime="text/html",
    )
    st.download_button(
        "Download voter links CSV",
        pd.DataFrame(rows).to_csv(index=False),
        file_name="voter_links.csv",
        mime="text/csv",
    )


def render_admin() -> None:
    st.markdown('<div class="hero"><div class="eyebrow">Admin</div><h1>Board Election Console</h1></div>', unsafe_allow_html=True)

    expected_password = current_secret("ADMIN_PASSWORD")
    if not expected_password:
        st.warning("Set `ADMIN_PASSWORD` in Streamlit secrets to enable the admin dashboard.")
        return

    if not st.session_state.get("admin_authenticated"):
        if expected_password == "admin":
            st.caption("Local dev password: `admin`")
        with st.form("admin_login"):
            password = st.text_input("Admin password", type="password")
            submitted = st.form_submit_button("Sign in")
        if submitted:
            if password == expected_password:
                st.session_state["admin_authenticated"] = True
                st.rerun()
            st.error("Invalid password.")
        return

    try:
        elections = db.fetch_elections()
    except Exception:
        friendly_db_error()
        return

    st.caption(f"Storage: `{db.backend_name()}`")
    if db.backend_name() == "Local SQLite":
        st.info(
            "No Supabase account needed for local testing. This app is saving elections and ballots "
            "to `.data/rcv.sqlite` on this computer. For Streamlit Cloud, use Supabase or another hosted database."
        )

    create_tab, manage_tab = st.tabs(["Create Election", "Manage Election"])

    with create_tab:
        st.info(
            "Creating an election adds a new, separate election. Existing elections, voters, ballots, and results are kept."
        )
        with st.form("create_election"):
            title = st.text_input("Election title", placeholder="2026 Board Election")
            seats = st.number_input("Seats available", min_value=1, max_value=50, value=1, step=1)
            candidate_raw = st.text_area(
                "Candidates",
                placeholder="Ada Lovelace | Finance committee chair\nGrace Hopper | Product strategy advisor",
                height=180,
                help="Enter one candidate per line. Optional bios can be added after a pipe character.",
            )
            submitted = st.form_submit_button("Create Separate Active Election")

        if submitted:
            candidates = parse_candidates(candidate_raw)
            if not title.strip() or len(candidates) < seats:
                st.warning("Add an election title and at least as many candidates as seats.")
            else:
                try:
                    election_id = db.create_election(title.strip(), int(seats), candidates)
                    st.success("Election created.")
                    st.session_state["selected_election_id"] = election_id
                    st.rerun()
                except Exception:
                    st.error("Election creation failed. Please check your Supabase connection and schema.")

    with manage_tab:
        if not elections:
            st.info("Create an election to begin.")
            return

        election_options = {f"{row['title']} ({row['status']})": row["id"] for row in elections}
        default_id = st.session_state.get("selected_election_id")
        option_labels = list(election_options.keys())
        default_index = 0
        if default_id:
            for index, label in enumerate(option_labels):
                if election_options[label] == default_id:
                    default_index = index
                    break

        selected_label = st.selectbox(
            "Election to manage",
            option_labels,
            index=default_index,
            help="Each election is separate. Selecting one here does not overwrite the others.",
        )
        election_id = election_options[selected_label]
        st.session_state["selected_election_id"] = election_id

        try:
            election = db.fetch_election(election_id)
            voters = db.fetch_voters(election_id)
        except Exception:
            st.error("Could not load this election.")
            return

        if not election:
            st.error("Election not found.")
            return

        cols = st.columns(4)
        cols[0].metric("Status", election["status"].title())
        cols[1].metric("Seats", election["seats_available"])
        cols[2].metric("Voters", len(voters))
        cols[3].metric("Ballots Cast", sum(1 for voter in voters if voter["has_voted"]))

        control_cols = st.columns([1, 1, 2])
        new_visibility = control_cols[0].toggle(
            "Publish Results to Voters",
            value=bool(election["results_visible"]),
        )
        if new_visibility != bool(election["results_visible"]):
            db.update_results_visibility(election_id, new_visibility)
            st.rerun()

        new_status = control_cols[1].selectbox(
            "Status",
            ["draft", "active", "completed"],
            index=["draft", "active", "completed"].index(election["status"]),
        )
        if new_status != election["status"]:
            db.update_election_status(election_id, new_status)
            st.rerun()

        auto_refresh = st.toggle(
            "Auto-refresh results every 10 seconds",
            value=True,
            help="Leave this on during the Zoom vote so the admin dashboard updates as ballots come in.",
        )
        if auto_refresh:
            if st_autorefresh is not None:
                st_autorefresh(interval=10_000, key=f"admin-refresh-{election_id}")
                st.caption("Auto-refresh is on. Ballots and results update about every 10 seconds.")
            else:
                st.caption("Auto-refresh will turn on after Streamlit installs the latest requirements. Until then, refresh the page.")

        with st.expander("Add voters", expanded=not voters):
            with st.form("add_voters"):
                voter_raw = st.text_area(
                    "Paste voter names",
                    placeholder="Alex Johnson\nSam Rivera\nJordan Lee",
                    height=140,
                    help="Enter one person per line. The app will generate one private voting link per name.",
                )
                submitted = st.form_submit_button("Generate Voting Links")
            if submitted:
                voter_labels = parse_voter_labels(voter_raw)
                if not voter_labels:
                    st.warning("Add at least one voter name.")
                else:
                    try:
                        db.add_voters(election_id, voter_labels)
                        st.success(f"Generated {len(voter_labels)} voting links.")
                        st.rerun()
                    except Exception:
                        st.error("Could not add voter links. Check your database connection and try again.")

        st.subheader("Voter Links")
        render_link_table(voters)

        st.divider()
        render_results(election)


def main() -> None:
    inject_css()
    token = st.query_params.get("token")
    route = st.query_params.get("route", "").lower()

    if token:
        render_voter(token)
        return

    if route == "admin":
        render_admin()
        return

    st.markdown(
        """
        <div class="hero">
            <div class="eyebrow">Secure board elections</div>
            <h1>Ranked-Choice Voting</h1>
            <p class="muted">Use a unique voting link to cast a ballot, or open the admin console to manage an election.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    col1, col2 = st.columns([1, 2])
    with col1:
        if st.button("Open Admin Console", type="primary"):
            st.query_params["route"] = "admin"
            st.rerun()
    with col2:
        st.markdown('<div class="callout">Voting links look like <code>?token=YOUR-UUID</code> and can only be used once.</div>', unsafe_allow_html=True)


if __name__ == "__main__":
    main()
