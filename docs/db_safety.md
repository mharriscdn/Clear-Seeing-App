# DB Safety

This is the simple, no-bullshit workflow to avoid breaking production.

---

## SETUP

- **Prod DB (Neon)** → source of truth
- **Neon Branch** → temporary safe copy
- **Code Branch** → your feature work

---

## WORKFLOW

### 1. CREATE BRANCH (BEFORE ANY CHANGES)

In Neon:
- Go to Branches
- Click Create branch
- Name it: `feature-xyz-YYYY-MM-DD`

This is an exact copy of production at that moment.

### 2. POINT YOUR APP TO THE BRANCH

Update your environment variable:

```
DATABASE_URL = <branch connection string>
```

Now your app is using the branch, NOT production.

### 3. DO YOUR WORK

- Run the app
- Test flows
- Make schema changes if needed
- Break things safely

Production is untouched.

### 4. VERIFY BEFORE MERGE

Before deploying, confirm:
- End-to-end flows work
- Billing works (if touched)
- Session flow works

Ask yourself: *Would I be comfortable running this on production right now?*

If not, keep working.

### 5. SWITCH BACK TO PROD DB

Before deploying:

```
DATABASE_URL = <PROD Neon URL>
```

### 6. DEPLOY CODE

Deploy your code normally.

**IMPORTANT:**
- You are deploying code only
- NOT copying data from the branch

### 7. APPLY DB CHANGES (IF ANY)

If you made schema changes:
- Run migrations on production DB
- Do NOT copy data from branch

### 8. DELETE BRANCH

After successful deploy, delete the Neon branch.

---

## RULES (DO NOT BREAK THESE)

1. **NEVER COPY DATA FROM BRANCH TO PROD** — Only schema moves forward.
2. **ALWAYS SWITCH DATABASE_URL BEFORE DEPLOY** — This is the most common mistake.
3. **NEVER TEST RISKY CHANGES ON PROD** — Always use a branch.

---

## FAST VERSION

Branch → point app → test → switch back → deploy → delete branch

---

## COMMON MISTAKES

- Forgetting to switch back to prod DB
- Running migrations on the wrong DB
- Treating branch as something to merge data from

---

## CORE PRINCIPLE

Branch = safe testing. Prod = real data.

You move code forward. You do NOT move data backward.

---

**ONE-LINE SUMMARY:** Branch for safety. Test there. Deploy code only. Never move data back.
