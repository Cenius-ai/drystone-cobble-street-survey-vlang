# Using Drystone Cobble Street Survey

Open `/` (or `/login`) and sign in with `cenius@cenius.ai` / `cenius`. `/`
always answers with a rendered page: the sign-in card while you are signed out,
the dashboard once the session is established. Every screen below is reachable
from the sticky top navigation; all other routes redirect to `/login` when
there is no session.

## The register in one paragraph

A **street** is registered first. **Patches** (loose cobble sets) hang from a
street and carry a sett count, a severity and an open/repaired status.
**Repair jobs** are raised from a patch, assign one active **crew**, and carry
their own sett count (defaulted from the patch), a status and — on a heritage
conservation area street — a heritage consent reference.

## Dashboard (`/`)

- Open-patch tile counts every patch whose status is not `repaired`.
- Setts-outstanding tile sums the setts across those open patches.
- Streets tile counts the register and how many are heritage conservation areas.
- Repair jobs tile breaks the register down by status (planned, scheduled,
  in progress, complete, blocked) with a bar row per status that links straight
  into the filtered job list.
- Consent-gap tile counts jobs on a conservation-area street with a blank
  consent reference, across **all** statuses — planned jobs included — and lists
  the affected jobs.
- The two recent-activity tables link into patch and job detail pages.

## Streets (`/streets`, `/streets/{id}`)

1. Use the filter rail (search, heritage status, sort) — the URL keeps your
   filters, so a filtered list is bookmarkable.
2. Register a street with the form at the bottom of the page. Street names are
   unique and checked server-side; blank names are rejected with a field message.
3. On the street page you can edit the name, district, notes and the heritage
   conservation area flag, and log a patch underneath it.
4. **Delete** a street only when it has no patches and no jobs; otherwise the
   page explains exactly what still references it.

## Patches (`/patches/{id}`)

1. The add-patch form on the street page takes a location description, a
   positive sett count, a severity, an open/repaired status and a discovery date.
   A sett count of `0`, a negative number or a forged status is rejected and no
   row is written.
2. The patch page shows the record, every job raised against it, an edit form
   (including the status select) and the raise-a-job form with the sett count
   already filled from the patch total.
3. Marking a patch `repaired` immediately lowers the dashboard open-patch count.
4. **Delete** a patch only when no job references it.

## Crews (`/crews`, `/crews/{id}`)

- Add a crew with a name and a foreman; new crews start active.
- The crew page edits the name and foreman, lists every job assigned to it, and
  toggles the crew **inactive** — which hides it from every job assignment
  select while keeping its job history. Forged POSTs that reference an inactive
  crew are rejected server-side.
- **Delete** a crew only when no job references it (deactivate instead to keep
  the history).

## Repair jobs (`/jobs`, `/jobs/{id}`, `/jobs/new`)

1. Raise a job from a patch page, or from `/jobs/new` (choose the patch there —
   the sett count prefills).
2. The job list filters by status and street and shows the patch, street, crew,
   setts, consent reference and status for each job.
3. The job page edits the crew, sett count, status, scheduled date, consent
   reference and notes, and deletes the job (which frees its patch for deletion).
4. **Heritage consent gate:** if the patch belongs to a conservation-area
   street, moving the job to `scheduled`, `in-progress` or `complete` without a
   consent reference returns the form with a field error and saves nothing. The
   same rule applies to a job created directly in one of those statuses.
   `planned` and `blocked` jobs save without a reference, and the dashboard
   consent-gap count tracks the outstanding ones.

## Signing out

`Log out` in the top-right clears the signed session; every app route then
redirects to the login page and preserves the page you asked for so you land
back on it after signing in.
