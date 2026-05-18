from __future__ import annotations

import re
from urllib.parse import quote

import pandas as pd
import plotly.express as px
import streamlit as st

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


def parse_emails(raw: str) -> list[str]:
    emails = []
    seen = set()
    for item in re.split(r"[\s,;]+", raw):
        email = item.strip().lower()
        if not email or email in seen:
            continue
        if re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            emails.append(email)
            seen.add(email)
    return emails


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


def render_results(election: dict) -> None:
    results = fetch_results(election["id"], election["seats_available"])
    st.subheader("Live RCV Results")

    metric_cols = st.columns(3)
    metric_cols[0].metric("Ballots Cast", results["total_ballots"])
    metric_cols[1].metric("Seats", election["seats_available"])
    metric_cols[2].metric("Droop Quota", results["quota"])

    if results["winners"]:
        winner_html = "".join(
            f'<span class="winner-pill">{winner["candidate"]}</span>' for winner in results["winners"]
        )
        st.markdown(winner_html, unsafe_allow_html=True)
    else:
        st.info("No winners yet. Results will appear as ballots are cast.")

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

    candidate_names = {candidate["name"]: candidate["id"] for candidate in candidates}
    available_names = list(candidate_names.keys())
    selected: list[str] = []

    with st.form("ballot_form"):
        for rank in range(1, len(candidates) + 1):
            choices = ["No selection"] + [name for name in available_names if name not in selected]
            choice = st.selectbox(f"Rank {rank}", choices, key=f"rank_{rank}")
            if choice != "No selection":
                selected.append(choice)

        confirm = st.checkbox("I confirm this ranking is final and my link will be marked as used.")
        submitted = st.form_submit_button("Submit Ballot", type="primary")

    if submitted:
        if not selected:
            st.warning("Please rank at least one candidate before submitting.")
            return
        if not confirm:
            st.warning("Please confirm your ballot before submitting.")
            return

        ranking = [candidate_names[name] for name in selected]
        try:
            db.submit_ballot(voter["id"], election["id"], ranking)
            st.session_state["submitted_token"] = token
            st.rerun()
        except Exception:
            st.error("We could not submit your ballot. Please refresh and try again.")


def render_link_table(voters: list[dict]) -> None:
    if not voters:
        st.info("No voters have been added yet.")
        return

    rows = []
    for voter in voters:
        token = voter["token"]
        link = f"{app_base_url()}/?token={quote(token)}"
        rows.append(
            {
                "Email": voter["email"],
                "Voting Link": link,
                "Voted": "Yes" if voter["has_voted"] else "No",
            }
        )
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
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
        with st.form("create_election"):
            title = st.text_input("Election title", placeholder="2026 Board Election")
            seats = st.number_input("Seats available", min_value=1, max_value=50, value=1, step=1)
            candidate_raw = st.text_area(
                "Candidates",
                placeholder="Ada Lovelace | Finance committee chair\nGrace Hopper | Product strategy advisor",
                height=180,
                help="Enter one candidate per line. Optional bios can be added after a pipe character.",
            )
            submitted = st.form_submit_button("Create Active Election")

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

        selected_label = st.selectbox("Election", option_labels, index=default_index)
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

        with st.expander("Add voters", expanded=not voters):
            with st.form("add_voters"):
                voter_raw = st.text_area(
                    "Paste voter emails",
                    placeholder="alex@example.com\nsam@example.com\njordan@example.com",
                    height=140,
                )
                submitted = st.form_submit_button("Generate Voting Links")
            if submitted:
                emails = parse_emails(voter_raw)
                if not emails:
                    st.warning("No valid email addresses were found.")
                else:
                    try:
                        db.add_voters(election_id, emails)
                        st.success(f"Generated {len(emails)} voting links.")
                        st.rerun()
                    except Exception:
                        st.error("Could not add voters. Check for duplicate rows or database constraints.")

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
