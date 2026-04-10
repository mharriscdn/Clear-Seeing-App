CLEAR BEING APP
DB Safety Guide
Version 1 — March 2026
This is the simple, no-bullshit workflow to avoid breaking production. Read it before touching anything database-related.
SETUP
•	Prod DB (Neon) — source of truth. All real sessions, billing, users.
•	Neon Branch — temporary safe copy. Exact snapshot of prod at a moment in time.
•	Code Branch — your feature work in Git.
•	Workspace DATABASE_URL — must point to Neon prod. Not helium.
⚠ IMPORTANT: Workspace and deployment must both point to the same Neon DB. If they differ, you are debugging a database your users never see.
THE WORKFLOW — DO THIS EVERY TIME
Step 1 — Create Neon Branch (before any changes)
In Neon dashboard: Branches → Create branch. Name it:
feature-xyz-YYYY-MM-DD
This is an exact copy of production at that moment. Production is untouched.
Step 2 — Point Workspace to Branch
Update workspace DATABASE_URL to the branch connection string. Now your app is using the branch, NOT production.
Step 3 — Do Your Work
•	Run the app
•	Test flows
•	Make schema changes if needed
•	Break things safely
Production is untouched.
Step 4 — Verify Before Deploy
•	End-to-end flows work
•	Billing works if touched
•	Session flow works
Ask yourself: would I be comfortable running this on production right now? If not, keep working.
Step 5 — Switch Back to Prod DB
⚠ This is the most common mistake. Do not skip this step.
DATABASE_URL = <PROD Neon URL>
Step 6 — Deploy Code
Deploy code normally. You are deploying CODE ONLY. Not copying data from the branch.
Step 7 — Apply Schema Changes (if any)
If you made schema changes, run migrations on the production DB. Do NOT copy data from branch.
Step 8 — Delete Branch
After successful deploy, delete the Neon branch. Done.
FAST VERSION — MEMORIZE THIS
Branch → point app → test → switch back → deploy → delete branch
RULES — DO NOT BREAK THESE
1. NEVER copy data from branch to prod. Only schema moves forward.
2. ALWAYS switch DATABASE_URL back to prod before deploy.
3. NEVER test risky changes directly on prod. Always branch first.
COMMON MISTAKES
•	Forgetting to switch DATABASE_URL back to prod before deploying
•	Running migrations on the wrong database
•	Treating branch data as something to merge back
•	Trusting workspace shell queries when DATABASE_URL points to wrong DB
HOW WE LEARNED THIS — MARCH 2026
For weeks the workspace DATABASE_URL pointed to helium (Replit internal dev DB). The deployed app pointed to Neon. They were two completely different databases.
Result: every workspace shell query showed an empty dev database. All verification of billing, sessions, token counts, and capacity deduction was against data that users never saw. The agent repeatedly gave false confidence because it was reading the wrong DB.
Fix: workspace DATABASE_URL now points to Neon. One DB. One truth.
Lesson: always confirm workspace and deployment point to the same database before trusting any query result.
CORE PRINCIPLE
Branch = safe testing. Prod = real data. You move CODE forward. You do NOT move data backward.
ONE-LINE SUMMARY
Branch for safety. Test there. Deploy code only. Never move data back.
