# Ground Zero user acceptance checklist

Use this checklist before accepting a Ground Zero release. Test with a disposable development or test database, never production data.

## Business clarity

- [ ] A new steward understands that a landscape is a business-first map rather than a technical inventory.
- [ ] Landscape name, domain, owner, and purpose use language familiar to the business.
- [ ] Functions, concepts, processes, departments, and systems remain visibly distinct.
- [ ] Uncertain system information can be recorded without presenting it as confirmed fact.
- [ ] Empty states explain the next useful action without requiring governance expertise.

## Complete steward journey

- [ ] Create a named landscape and confirm it survives refresh.
- [ ] Add and edit a business function, concept, process, and department or unit.
- [ ] Add a system and record its knowledge status.
- [ ] Connect a business function to a system.
- [ ] Confirm completion guidance identifies missing, duplicate, and unconnected items.
- [ ] Enter partial work, refresh, resume it, and either save or discard it.
- [ ] Reach “Landscape ready for next step.”
- [ ] Create handoff tasks once and confirm repeating the action creates no duplicates.
- [ ] Follow the handoff into understanding, official-source review, quality, and approval.

## Role behavior

- [ ] Steward sees construction and relationship-mapping controls.
- [ ] Approver sees readiness and governance information without mutation controls.
- [ ] Administrator sees landscape-health guidance and authorized intervention controls.
- [ ] Direct unauthorized API mutations return `403`, even if UI controls are bypassed.

## Usability and resilience

- [ ] Labels use business language and can be understood without technical training.
- [ ] Validation errors identify what must be corrected.
- [ ] Refreshing or navigating away does not silently lose partial work.
- [ ] Destructive actions request confirmation and checkpoints can restore prior state.
- [ ] Keyboard navigation reaches forms, tabs, relationship controls, and handoff actions in a logical order.
- [ ] The workflow remains usable at common desktop and mobile widths.

## Automated evidence

Run:

```bash
cd backend
../.venv/bin/python -m pytest -q

cd ../frontend
npm run build
npm run test:e2e
```

Acceptance requires all commands to pass and all applicable checklist items to be checked.
