# TRADERS OS — connected education ecosystem

[Open the presentation demo](https://techanika-dev.github.io/traders-os-demo/) · [Project proposal](https://techanika-dev.github.io/traders-os-demo/proposal/)

The public GitHub Pages version is an interactive **browser-only presentation demo**. All accounts, progress, feedback, enquiries and simulated subscriptions stay in the browser where they are created. They are not shared across devices or sent to a real academy. Use fictional details and a demo-only password. No payment is taken.

## Try the journey

1. Create a student account and choose a course or Professional plan.
2. Confirm demo checkout, complete a lesson and submit an assignment.
3. In another tab in the same browser, open sign-in → Explore staff and sample student demos → Tutor. Grade the submitted work.
4. Return to the student's tab to see the saved feedback.
5. In My membership, try cancellation. Individually purchased courses remain available.

Sample staff sign-in uses `tutor@demo.vertex`, `admin@demo.vertex` or `superadmin@demo.vertex` with `VertexDemo`. These public sample credentials are exclusively for fictional demonstration data. Student demo: `student@demo.vertex`.

## Connected local backend

The `connected-source` folder includes the Python/SQLite account-backed implementation, frontend source, build configuration, fictional seed data and compiled local HTML. No live database, password hashes, session tokens or user records from the development environment are published.

```sh
cd connected-source
python unified-server.py
```

Open `http://127.0.0.1:8766`. Python uses only its standard library. To rebuild the frontend, use `npm install` then `npm run build` in the same folder. The compiled local app is already included, so rebuilding is optional.

The local backend uses scrypt password hashing, expiring sessions, student-scoped state and checkout-based access grants. It is a prototype: replace public demo staff access, add production identity/recovery and abuse controls, and integrate a payment provider before hosting real accounts. GitHub Pages cannot run this backend; a suitable application host and persistent storage are required for cross-device accounts.

## Preserved work

The previous public prototype is at `previous-demo.html`. The existing `proposal/` site remains unchanged. Research includes 252 feature entries and 22 implementation modules. Simulated integrations, prices and learning records are not live service capabilities.
