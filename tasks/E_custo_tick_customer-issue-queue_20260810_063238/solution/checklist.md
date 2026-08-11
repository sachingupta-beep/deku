# Checklist: Ethara Customer Issue Queue

Source: instruction.md
Sections present: overview, roles, features, flow, uiux, constraints, deployment, technical, datamodel
Sections absent: buildplan
Items: 173
Unpinned values flagged: 1

## C-OV Overview

- [ ] `C-OV-01` `capability` The app lets a customer raise an issue into a shared queue. `src: Overview para 1`
- [ ] `C-OV-02` `capability` The app lets an agent take sole ownership of a queued ticket. `src: Overview para 1`
- [ ] `C-OV-03` `capability` The app lets a supervisor move a ticket to a different agent. `src: Overview para 1`
- [ ] `C-OV-04` `capability` The app emails the raising customer whenever ownership changes. `src: Overview para 1`
- [ ] `C-OV-05` `constraint` The app persists exactly one assignment when two agents claim simultaneously. `src: Overview para 2`
- [ ] `C-OV-06` `constraint` The app delivers exactly one email when two agents claim simultaneously. `src: Overview para 2`
- [ ] `C-OV-07` `constraint` The app offers no comment feature. `src: Overview para 3`
- [ ] `C-OV-08` `constraint` The app offers no attachment feature. `src: Overview para 3`
- [ ] `C-OV-09` `constraint` The app offers no reopening feature. `src: Overview para 3`
- [ ] `C-OV-10` `constraint` The app offers no search feature. `src: Overview para 3`

## C-RL User roles

- [ ] `C-RL-01` `role` A customer reads only tickets the customer raised. `src: User roles table row 1`
- [ ] `C-RL-02` `role` A customer creates a ticket. `src: User roles table row 1`
- [ ] `C-RL-03` `constraint` A customer claims no ticket. `src: User roles table row 1`
- [ ] `C-RL-04` `constraint` A customer reassigns no ticket. `src: User roles table row 1`
- [ ] `C-RL-05` `constraint` A customer resolves no ticket. `src: User roles table row 1`
- [ ] `C-RL-06` `role` An agent reads the open queue. `src: User roles table row 2`
- [ ] `C-RL-07` `role` An agent reads tickets assigned to that agent. `src: User roles table row 2`
- [ ] `C-RL-08` `role` An agent claims a ticket in status `open`. `src: User roles table row 2`
- [ ] `C-RL-09` `role` An agent resolves a ticket assigned to that agent. `src: User roles table row 2`
- [ ] `C-RL-10` `constraint` An agent reassigns no ticket. `src: User roles table row 2`
- [ ] `C-RL-11` `constraint` An agent reads no ticket assigned to another agent. `src: User roles table row 2`
- [ ] `C-RL-12` `role` A supervisor reads every ticket. `src: User roles table row 3`
- [ ] `C-RL-13` `role` A supervisor reassigns any ticket in status `assigned`. `src: User roles table row 3`
- [ ] `C-RL-14` `role` A supervisor resolves any ticket in status `assigned`. `src: User roles table row 3`
- [ ] `C-RL-15` `constraint` A supervisor raises no ticket. `src: User roles table row 3`
- [ ] `C-RL-16` `constraint` The app enforces authorization server side on every mutating endpoint. `src: User roles para 2`
- [ ] `C-RL-17` `constraint` The app rejects an agent call to a supervisor only endpoint with status 401 or 403. `src: User roles para 2`
- [ ] `C-RL-18` `constraint` The app leaves the database row unchanged after a rejected call. `src: User roles para 2`
- [ ] `C-RL-19` `constraint` The app returns status 403 when an agent acts on another agent's ticket. `src: User roles para 3`
- [ ] `C-RL-20` `constraint` The app returns status 403 when a customer reads another customer's ticket. `src: User roles para 3`
- [ ] `C-RL-21` `constraint` The app exposes no registration route. `src: User roles para 4`
- [ ] `C-RL-22` `literal` The app seeds the account `customer@example.com`. `src: User roles para 4`
- [ ] `C-RL-23` `literal` The app seeds the account `customer2@example.com`. `src: User roles para 4`
- [ ] `C-RL-24` `literal` The app seeds the account `agent@example.com`. `src: User roles para 4`
- [ ] `C-RL-25` `literal` The app seeds the account `agent2@example.com`. `src: User roles para 4`
- [ ] `C-RL-26` `literal` The app seeds the account `supervisor@example.com`. `src: User roles para 4`

## C-CF Core features

- [ ] `C-CF-01` `contract` The app accepts email plus password at `/api/auth/login`. `src: Core features, Auth para`
- [ ] `C-CF-02` `capability` The app returns a bearer token on successful login. `src: Core features, Auth para`
- [ ] `C-CF-03` `constraint` The app stores every password hashed at rest. `src: Core features, Auth para`
- [ ] `C-CF-04` `literal` The app accepts the password `deku-demo-pw-2026` for every seeded account. `src: Core features rule 1`
- [ ] `C-CF-05` `capability` The app returns the user role on successful login. `src: Core features rule 1`
- [ ] `C-CF-06` `constraint` The app rejects a wrong password with status 401. `src: Core features rule 1`
- [ ] `C-CF-07` `constraint` The app returns no token after a wrong password. `src: Core features rule 1`
- [ ] `C-CF-08` `capability` The app stores a new ticket with status `open`. `src: Core features rule 2`
- [ ] `C-CF-09` `capability` The app stores a new ticket with no assignee. `src: Core features rule 2`
- [ ] `C-CF-10` `data` The app sets `customer_id` on a new ticket to the raising customer. `src: Core features rule 2`
- [ ] `C-CF-11` `constraint` The app rejects a ticket with an empty title using status 422. `src: Core features rule 2`
- [ ] `C-CF-12` `constraint` The app rejects a ticket with an empty body using status 422. `src: Core features rule 2`
- [ ] `C-CF-13` `constraint` The app returns status 403 when an agent raises a ticket. `src: Core features rule 3`
- [ ] `C-CF-14` `contract` The app returns a top level JSON array from `/api/tickets`. `src: Core features rule 4`
- [ ] `C-CF-15` `data` The app orders the ticket list newest first by `created_at`. `src: Core features rule 4`
- [ ] `C-CF-16` `capability` The app sets ticket status to `assigned` on a successful claim. `src: Core features rule 5`
- [ ] `C-CF-17` `capability` The app sets `assignee_id` to the claiming agent on a successful claim. `src: Core features rule 5`
- [ ] `C-CF-18` `constraint` The app persists the assignment before responding with success. `src: Core features rule 5`
- [ ] `C-CF-19` `constraint` The app rejects a claim on an already assigned ticket with status 409. `src: Core features rule 5`
- [ ] `C-CF-20` `constraint` The app leaves `assignee_id` unchanged after a rejected claim. `src: Core features rule 5`
- [ ] `C-CF-21` `constraint` The app grants only one of two simultaneous claims on one ticket. `src: Core features rule 6`
- [ ] `C-CF-22` `constraint` The app rejects the losing simultaneous claim with status 409. `src: Core features rule 6`
- [ ] `C-CF-23` `constraint` The app stores the winning agent as `assignee_id` after simultaneous claims. `src: Core features rule 6`
- [ ] `C-CF-24` `constraint` The app never stores status `assigned` together with a null assignee. `src: Core features rule 6`
- [ ] `C-CF-25` `constraint` The app returns status 403 when a customer calls the claim endpoint. `src: Core features rule 7`
- [ ] `C-CF-26` `capability` The app sets `assignee_id` to the named agent on a supervisor reassign. `src: Core features rule 8`
- [ ] `C-CF-27` `constraint` The app keeps ticket status `assigned` after a reassign. `src: Core features rule 8`
- [ ] `C-CF-28` `constraint` The app rejects a reassign naming the current holder with status 409. `src: Core features rule 8`
- [ ] `C-CF-29` `constraint` The app rejects a reassign naming a non agent user with status 422. `src: Core features rule 8`
- [ ] `C-CF-30` `constraint` The app returns status 403 when an agent calls the reassign endpoint. `src: Core features rule 9`
- [ ] `C-CF-31` `constraint` The app leaves the assignee unchanged after a rejected reassign. `src: Core features rule 9`
- [ ] `C-CF-32` `capability` The app delivers one email over SMTP on each persisted assignment change. `src: Core features rule 10`
- [ ] `C-CF-33` `data` The app addresses the assignment email to the raising customer. `src: Core features rule 10`
- [ ] `C-CF-34` `constraint` The app sets no cc recipient on the assignment email. `src: Core features rule 10`
- [ ] `C-CF-35` `constraint` The app sets no bcc recipient on the assignment email. `src: Core features rule 10`
- [ ] `C-CF-36` `constraint` The app excludes the assigned agent from the email recipients. `src: Core features rule 10`
- [ ] `C-CF-37` `literal` The app begins the email subject with `Ticket assigned: `. `src: Core features rule 11`
- [ ] `C-CF-38` `data` The app appends the ticket title to the email subject. `src: Core features rule 11`
- [ ] `C-CF-39` `data` The app names the assigned agent in the email body. `src: Core features rule 11`
- [ ] `C-CF-40` `constraint` The app delivers no email when a customer raises a ticket. `src: Core features rule 12`
- [ ] `C-CF-41` `constraint` The app delivers no email when a ticket becomes `resolved`. `src: Core features rule 12`
- [ ] `C-CF-42` `constraint` The app delivers no email after a rejected claim. `src: Core features rule 12`
- [ ] `C-CF-43` `capability` The app sets ticket status to `resolved` for the assignee. `src: Core features rule 13`
- [ ] `C-CF-44` `constraint` The app rejects a resolve on a ticket in status `open` with status 409. `src: Core features rule 13`
- [ ] `C-CF-45` `constraint` The app rejects any transition out of status `resolved` with status 409. `src: Core features rule 13`

## C-UF User flow

- [ ] `C-UF-01` `contract` The app serves a sign in page at `/login`. `src: User flow route table row 1`
- [ ] `C-UF-02` `contract` The app serves the unowned queue at `/queue`. `src: User flow route table row 2`
- [ ] `C-UF-03` `contract` The app serves agent owned tickets at `/my-tickets`. `src: User flow route table row 3`
- [ ] `C-UF-04` `contract` The app serves every ticket at `/all-tickets`. `src: User flow route table row 4`
- [ ] `C-UF-05` `contract` The app serves an issue creation form at `/tickets/new`. `src: User flow route table row 5`
- [ ] `C-UF-06` `contract` The app serves one ticket detail at `/tickets/:id`. `src: User flow route table row 6`
- [ ] `C-UF-07` `constraint` The app redirects an unauthenticated request on a protected route to `/login`. `src: User flow, Entry para`
- [ ] `C-UF-08` `constraint` The app shows no protected data before redirecting an unauthenticated request. `src: User flow, Entry para`
- [ ] `C-UF-09` `capability` The app lands a customer on `/my-tickets` after login. `src: User flow, Entry para`
- [ ] `C-UF-10` `capability` The app lands an agent on `/queue` after login. `src: User flow, Entry para`
- [ ] `C-UF-11` `capability` The app lands a supervisor on `/all-tickets` after login. `src: User flow, Entry para`
- [ ] `C-UF-12` `capability` The app clears the bearer token on logout. `src: User flow, Entry para`
- [ ] `C-UF-13` `constraint` The app applies no change when a token expires mid action. `src: User flow, Entry para`
- [ ] `C-UF-14` `constraint` The app shows a not permitted state on a route the role lacks. `src: User flow, Entry para`
- [ ] `C-UF-15` `ui` The app shows `No unclaimed tickets` on an empty queue. `src: User flow, States para`
- [ ] `C-UF-16` `ui` The app shows `Nothing assigned to you` for an agent with no owned ticket. `src: User flow, States para`
- [ ] `C-UF-17` `ui` The app shows `You haven't raised any issues yet` for a customer with no ticket. `src: User flow, States para`
- [ ] `C-UF-18` `ui` The app shows a loading state on every page. `src: User flow, States para`
- [ ] `C-UF-19` `ui` The app leaves the visible state unchanged after a refused action. `src: User flow, States para`
- [ ] `C-UF-20` `ui` The app shows an inline reason after a refused action. `src: User flow, States para`

## C-UX UI and UX notes

- [ ] `C-UX-01` `ui` The app uses background colour `#F7F8FA`. `src: UI/UX notes, Palette para`
- [ ] `C-UX-02` `ui` The app uses surface colour `#FFFFFF`. `src: UI/UX notes, Palette para`
- [ ] `C-UX-03` `ui` The app uses primary text colour `#101828`. `src: UI/UX notes, Palette para`
- [ ] `C-UX-04` `ui` The app uses call to action colour `#1F6FEB`. `src: UI/UX notes, Palette para`
- [ ] `C-UX-05` `ui` The app uses danger colour `#D92D20`. `src: UI/UX notes, Palette para`
- [ ] `C-UX-06` `ui` The app renders body text at `14px/20px`. `src: UI/UX notes, Type para`
- [ ] `C-UX-07` `ui` The app uses the font family `Inter`. `src: UI/UX notes, Type para`
- [ ] `C-UX-08` `ui` The app uses tabular numerals where numbers align. `src: UI/UX notes, Type para`
- [ ] `C-UX-09` `ui` The app rounds cards to `8px`. `src: UI/UX notes, Shape para`
- [ ] `C-UX-10` `ui` The app sets table row height to `44px`. `src: UI/UX notes, Shape para`
- [ ] `C-UX-11` `ui` The app runs standard transitions at `150ms`. `src: UI/UX notes, Motion para`
- [ ] `C-UX-12` `ui` The app honours `prefers-reduced-motion` by dropping transitions to `0ms`. `src: UI/UX notes, Motion para`
- [ ] `C-UX-13` `ui` The app collapses the queue to stacked cards below `768`. `src: UI/UX notes, Responsive para`
- [ ] `C-UX-14` `ui` The app sizes touch targets at `44` pixels or larger. `src: UI/UX notes, Responsive para`
- [ ] `C-UX-15` `ui` The app meets a text contrast ratio of `4.5:1`. `src: UI/UX notes, Responsive para`
- [ ] `C-UX-16` `ui` The app shows a visible focus ring on every interactive element. `src: UI/UX notes, Responsive para`
- [ ] `C-UX-17` `ui` The app pairs every status colour with a status word. `src: UI/UX notes, Responsive para`

## C-TR Technical requirements

- [ ] `C-TR-01` `contract` The app reads its database connection from `DATABASE_URL`. `src: Technical requirements para 1`
- [ ] `C-TR-02` `contract` The app reads its mail host from `SMTP_HOST`. `src: Technical requirements para 1`
- [ ] `C-TR-03` `contract` The app reads its mail port from `SMTP_PORT`. `src: Technical requirements para 1`
- [ ] `C-TR-04` `contract` The app serves `/api/health` with status 200 once ready. `src: Technical requirements para 1`
- [ ] `C-TR-05` `constraint` The app starts no copy of PostgreSQL. `src: Technical requirements para 2`
- [ ] `C-TR-06` `constraint` The app starts no copy of Mailpit. `src: Technical requirements para 2`
- [ ] `C-TR-07` `constraint` The app hardcodes no service host. `src: Technical requirements para 2`
- [ ] `C-TR-08` `constraint` The app introduces no second database. `src: Technical requirements para 3`
- [ ] `C-TR-09` `constraint` The app introduces no external mail vendor. `src: Technical requirements para 3`
- [ ] `C-TR-10` `constraint` The app returns status in the 4xx range for a business rule violation. `src: Technical requirements para 4`
- [ ] `C-TR-11` `constraint` The app returns no 5xx status for a business rule violation. `src: Technical requirements para 4`

## C-DM Data model

- [ ] `C-DM-01` `data` The app stores every timestamp in UTC. `src: Data model para 1`
- [ ] `C-DM-02` `literal` The app accepts `deku-demo-pw-2026` at login for every seeded account. `src: Data model para 2`
- [ ] `C-DM-03` `contract` The app writes seeded credentials into `/app/USER_README.md`. `src: Data model para 2`
- [ ] `C-DM-04` `data` The app keeps user email addresses unique. `src: Data model, users para`
- [ ] `C-DM-05` `data` The app restricts the user role field to three named values. `src: Data model, users para`
- [ ] `C-DM-06` `data` The app restricts ticket status to `open`, `assigned`, `resolved`. `src: Data model, tickets para`
- [ ] `C-DM-07` `data` The app never changes `customer_id` after ticket creation. `src: Data model, tickets para`
- [ ] `C-DM-08` `data` The app computes the queue age column on read. `src: Data model, tickets para`
- [ ] `C-DM-09` `constraint` The app stores a null `assignee_id` exactly when status is `open`. `src: Data model, properties list`
- [ ] `C-DM-10` `constraint` The app allows at most one successful claim per ticket in status `open`. `src: Data model, properties list`
- [ ] `C-DM-11` `constraint` The app holds single claim behaviour under concurrent requests. `src: Data model, properties list`
- [ ] `C-DM-12` `constraint` The app follows every persisted assignee change with one delivered email. `src: Data model, properties list`
- [ ] `C-DM-13` `constraint` The app treats status `resolved` as terminal. `src: Data model, properties list`
- [ ] `C-DM-14` `literal` The app seeds ticket `Payment page returns 500` with status `open`. `src: Data model, seed para`
- [ ] `C-DM-15` `literal` The app seeds ticket `Export CSV missing columns` with status `open`. `src: Data model, seed para`
- [ ] `C-DM-16` `literal` The app seeds ticket `Login loop on mobile` with status `assigned`. `src: Data model, seed para`
- [ ] `C-DM-17` `data` The app seeds five user accounts. `src: Data model, seed para`
- [ ] `C-DM-18` `constraint` The app duplicates no row when seeding runs again. `src: Data model, seed para`

## C-CN Constraints

- [ ] `C-CN-01` `constraint` The app exposes no password reset feature. `src: Constraints para 1`
- [ ] `C-CN-02` `constraint` The app supports no ticket editing after creation. `src: Constraints para 1`
- [ ] `C-CN-03` `constraint` The app supports no ticket deletion. `src: Constraints para 1`
- [ ] `C-CN-04` `constraint` The app reads no inbound mail. `src: Constraints para 1`
- [ ] `C-CN-05` `constraint` The app uses no realtime push channel. `src: Constraints para 1`
- [ ] `C-CN-06` `constraint` The app makes no external network call beyond the two named backing services. `src: Constraints para 1`
- [ ] `C-CN-07` `constraint` The app stays responsive with 500 tickets. `src: Constraints para 1`

## C-DC Deployment contract

- [ ] `C-DC-01` `contract` The app becomes reachable at `APP_PUBLIC_URL`. `src: Deployment contract, bullet 1`
- [ ] `C-DC-02` `contract` The app reads its outside port from `APP_PUBLIC_PORT`. `src: Deployment contract, bullet 1`
- [ ] `C-DC-03` `contract` The app listens on container port `4173`. `src: Deployment contract, bullet 1`
- [ ] `C-DC-04` `contract` The app serves its HTTP API under the `/api` prefix. `src: Deployment contract, bullet 2`
- [ ] `C-DC-05` `contract` The app returns status 200 from `/api/health` once ready. `src: Deployment contract, bullet 3`
- [ ] `C-DC-06` `contract` The app starts from the environment image with no manual step. `src: Deployment contract, bullet 4`
- [ ] `C-DC-07` `contract` The app writes login credentials to `/app/USER_README.md`. `src: Deployment contract, bullet 5`
- [ ] `C-DC-08` `contract` The app creates an empty `.browser_screenshots/` directory at the app root. `src: Deployment contract, bullet 6`
- [ ] `C-DC-09` `contract` The app creates an empty `.downloads/` directory at the app root. `src: Deployment contract, bullet 6`
- [ ] `C-DC-10` `contract` The app serves a production build behind a preview server. `src: Deployment contract, bullet 7`
- [ ] `C-DC-11` `contract` The app keeps the server running after the session ends. `src: Deployment contract, bullet 8`
- [ ] `C-DC-12` `contract` The app runs the server outside the starting shell process tree. `src: Deployment contract, bullet 8`
- [ ] `C-DC-13` `contract` The app binds to `0.0.0.0`. `src: Deployment contract, bullet 9`
- [ ] `C-DC-14` `contract` The app uses no edge function. `src: Deployment contract, bullet 11`
- [ ] `C-DC-15` `contract` The app declares no persistent volume. `src: Deployment contract, bullet 12`
- [ ] `C-DC-16` `contract` The app returns the created ticket from `POST /api/tickets` with status 201. `src: Deployment contract, API shapes table`
- [ ] `C-DC-17` `contract` The app requires a bearer token on every endpoint except login. `src: Deployment contract, API shapes table`
- [ ] `C-DC-18` `constraint` The app stores tickets in PostgreSQL rather than in memory. `src: Deployment contract, No mocks para`
- [ ] `C-DC-19` `constraint` The app sends mail through a real SMTP conversation. `src: Deployment contract, No mocks para`

## Pinned literals

| Value | What it is | Item | Stated in |
|---|---|---|---|
| `deku-demo-pw-2026` | password for every seeded account | C-CF-04 | Core features rule 1 |
| `customer@example.com` | seeded customer account | C-RL-22 | User roles para 4 |
| `customer2@example.com` | second seeded customer account | C-RL-23 | User roles para 4 |
| `agent@example.com` | seeded agent account | C-RL-24 | User roles para 4 |
| `agent2@example.com` | second seeded agent account | C-RL-25 | User roles para 4 |
| `supervisor@example.com` | seeded supervisor account | C-RL-26 | User roles para 4 |
| `Ticket assigned: ` | assignment email subject prefix | C-CF-37 | Core features rule 11 |
| `Payment page returns 500` | seeded unowned ticket title | C-DM-14 | Data model seed para |
| `Export CSV missing columns` | second seeded unowned ticket title | C-DM-15 | Data model seed para |
| `Login loop on mobile` | seeded owned ticket title | C-DM-16 | Data model seed para |
| `open` | queued ticket status | C-DM-06 | Data model tickets para |
| `assigned` | owned ticket status | C-DM-06 | Data model tickets para |
| `resolved` | closed ticket status | C-DM-06 | Data model tickets para |
| `/app/USER_README.md` | credentials file path | C-DM-03 | Data model para 2 |
| `4173` | container internal port | C-DC-03 | Deployment contract bullet 1 |
| `0.0.0.0` | bind address | C-DC-13 | Deployment contract bullet 9 |
| `DATABASE_URL` | database connection variable | C-TR-01 | Technical requirements para 1 |
| `SMTP_HOST` | mail host variable | C-TR-02 | Technical requirements para 1 |
| `SMTP_PORT` | mail port variable | C-TR-03 | Technical requirements para 1 |
| `APP_PUBLIC_URL` | public app address variable | C-DC-01 | Deployment contract bullet 1 |
| `APP_PUBLIC_PORT` | public app port variable | C-DC-02 | Deployment contract bullet 1 |
| `/api/auth/login` | login endpoint | C-CF-01 | Core features Auth para |
| `/api/tickets` | ticket collection endpoint | C-CF-14 | Core features rule 4 |
| `/api/health` | health endpoint | C-TR-04 | Technical requirements para 1 |
| `/login` | sign in route | C-UF-01 | User flow route table row 1 |
| `/queue` | queue route | C-UF-02 | User flow route table row 2 |
| `/my-tickets` | agent owned ticket route | C-UF-03 | User flow route table row 3 |
| `/all-tickets` | supervisor route | C-UF-04 | User flow route table row 4 |
| `/tickets/new` | creation route | C-UF-05 | User flow route table row 5 |
| `/tickets/:id` | detail route | C-UF-06 | User flow route table row 6 |
| `#F7F8FA` | background colour | C-UX-01 | UI/UX notes palette para |
| `#FFFFFF` | surface colour | C-UX-02 | UI/UX notes palette para |
| `#101828` | primary text colour | C-UX-03 | UI/UX notes palette para |
| `#1F6FEB` | call to action colour | C-UX-04 | UI/UX notes palette para |
| `#D92D20` | danger colour | C-UX-05 | UI/UX notes palette para |
| `14px/20px` | body type size | C-UX-06 | UI/UX notes type para |
| `Inter` | font family | C-UX-07 | UI/UX notes type para |
| `8px` | card corner radius | C-UX-09 | UI/UX notes shape para |
| `44px` | table row height | C-UX-10 | UI/UX notes shape para |
| `150ms` | standard transition duration | C-UX-11 | UI/UX notes motion para |
| `prefers-reduced-motion` | reduced motion media feature | C-UX-12 | UI/UX notes motion para |
| `0ms` | reduced motion transition duration | C-UX-12 | UI/UX notes motion para |
| `768` | queue collapse breakpoint | C-UX-13 | UI/UX notes responsive para |
| `44` | minimum touch target size | C-UX-14 | UI/UX notes responsive para |
| `4.5:1` | minimum text contrast ratio | C-UX-15 | UI/UX notes responsive para |
| `No unclaimed tickets` | empty queue copy | C-UF-15 | User flow states para |
| `Nothing assigned to you` | empty agent list copy | C-UF-16 | User flow states para |
| `You haven't raised any issues yet` | empty customer list copy | C-UF-17 | User flow states para |
| `customer_id` | raiser column name | C-CF-10 | Core features rule 2 |
| `assignee_id` | assignee column name | C-CF-17 | Core features rule 5 |
| `created_at` | creation timestamp column name | C-CF-15 | Core features rule 4 |
| `.browser_screenshots/` | reserved screenshot directory | C-DC-08 | Deployment contract bullet 6 |
| `.downloads/` | reserved download directory | C-DC-09 | Deployment contract bullet 6 |
| `/api` | API path prefix | C-DC-04 | Deployment contract bullet 2 |
| `POST /api/tickets` | ticket creation endpoint | C-DC-16 | Deployment contract API shapes table |

### Referenced but not pinned

| What the instruction calls it | Item | Why it matters |
|---|---|---|
| the bearer token lifetime | C-UF-13 | expiry duration named by behaviour with no value given |

## Coverage ledger

| Section | Obligation-bearing sentences | Items produced |
|---|---|---|
| Overview | 6 | 10 |
| User roles | 12 | 26 |
| Core features | 26 | 45 |
| User flow | 15 | 20 |
| UI and UX notes | 12 | 17 |
| Technical requirements | 8 | 11 |
| Data model | 14 | 18 |
| Constraints | 5 | 7 |
| Deployment contract | 15 | 19 |
