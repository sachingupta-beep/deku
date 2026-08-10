# Checklist: Ethara - Kestrel Yard Allocation Board

Source: instruction.md
Sections present: Overview, User roles, Core features, User flow, UI and UX notes, Constraints, Technical requirements, Data model, Build plan, Deployment contract
Sections absent: none of the ten section codes is unused
Items: 362
Unpinned values flagged: 3

The instruction also carries a Definition of done section. Every ask in that section restates an ask stated earlier, so per the restatement rule the section produces no new item.

## C-OV Overview

- [ ] `C-OV-01` `capability` A planner reserves a quantity of one pallet item. `src: Overview para 1`
- [ ] `C-OV-02` `constraint` The on-hand count stays unchanged when a planner reserves stock. `src: Overview para 1`
- [ ] `C-OV-03` `capability` The held count rises by the reserved quantity. `src: Overview para 1`
- [ ] `C-OV-04` `capability` Free stock falls by the reserved quantity. `src: Overview para 1`
- [ ] `C-OV-05` `capability` A planner releases their own hold. `src: Overview para 1`
- [ ] `C-OV-06` `capability` Released stock returns to free stock. `src: Overview para 1`
- [ ] `C-OV-07` `capability` A stock admin moves the on-hand count by a signed delta. `src: Overview para 1`
- [ ] `C-OV-08` `constraint` An adjustment carries a written reason. `src: Overview para 1`
- [ ] `C-OV-09` `capability` An accepted reservation appends exactly one ledger line. `src: Overview para 2`
- [ ] `C-OV-10` `capability` An accepted release appends exactly one ledger line. `src: Overview para 2`
- [ ] `C-OV-11` `capability` An accepted adjustment appends exactly one ledger line. `src: Overview para 2`
- [ ] `C-OV-12` `constraint` No endpoint edits a ledger line. `src: Overview para 2`
- [ ] `C-OV-13` `constraint` No endpoint deletes a ledger line. `src: Overview para 2`
- [ ] `C-OV-14` `literal` A reservation taking free stock below `0` is refused. `src: Overview para 3`
- [ ] `C-OV-15` `capability` The reservation refusal states how many pallets are still free. `src: Overview para 3`
- [ ] `C-OV-16` `capability` An adjustment pushing on-hand below held stock is refused. `src: Overview para 3`

## C-RL User roles

- [ ] `C-RL-01` `role` The `planner` signs in. `src: User roles table row 1`
- [ ] `C-RL-02` `role` The `planner` reads the board. `src: User roles table row 1`
- [ ] `C-RL-03` `role` The `planner` reads the ledger. `src: User roles table row 1`
- [ ] `C-RL-04` `role` The `planner` reserves stock. `src: User roles table row 1`
- [ ] `C-RL-05` `role` The `planner` releases their own reservation. `src: User roles table row 1`
- [ ] `C-RL-06` `role` The `planner` lists their own reservations. `src: User roles table row 1`
- [ ] `C-RL-07` `constraint` The `planner` cannot adjust on-hand counts. `src: User roles table row 1`
- [ ] `C-RL-08` `role` The seed carries two planner accounts. `src: User roles table row 1`
- [ ] `C-RL-09` `role` The `stock_admin` signs in. `src: User roles table row 2`
- [ ] `C-RL-10` `role` The `stock_admin` reads the board. `src: User roles table row 2`
- [ ] `C-RL-11` `role` The `stock_admin` reads the ledger. `src: User roles table row 2`
- [ ] `C-RL-12` `role` The `stock_admin` adjusts on-hand counts. `src: User roles table row 2`
- [ ] `C-RL-13` `constraint` The `stock_admin` cannot reserve stock. `src: User roles table row 2`
- [ ] `C-RL-14` `constraint` The `stock_admin` cannot release a reservation. `src: User roles table row 2`
- [ ] `C-RL-15` `role` The seed carries one stock admin account. `src: User roles table row 2`
- [ ] `C-RL-16` `role` The `auditor` signs in. `src: User roles table row 3`
- [ ] `C-RL-17` `role` The `auditor` reads the board. `src: User roles table row 3`
- [ ] `C-RL-18` `role` The `auditor` reads the ledger. `src: User roles table row 3`
- [ ] `C-RL-19` `constraint` The `auditor` cannot reserve stock. `src: User roles table row 3`
- [ ] `C-RL-20` `constraint` The `auditor` cannot release a reservation. `src: User roles table row 3`
- [ ] `C-RL-21` `constraint` The `auditor` cannot adjust on-hand counts. `src: User roles table row 3`
- [ ] `C-RL-22` `role` The seed carries one auditor account. `src: User roles table row 3`
- [ ] `C-RL-23` `constraint` Authorization is enforced server-side on every mutating endpoint. `src: User roles para 2`
- [ ] `C-RL-24` `constraint` Hiding a button in the interface does not stand in for authorization. `src: User roles para 2`
- [ ] `C-RL-25` `literal` A direct API call from a `planner` session against a `stock_admin` endpoint is rejected with `401` or `403`. `src: User roles para 2`
- [ ] `C-RL-26` `constraint` The product carries no signup path. `src: User roles para 3`
- [ ] `C-RL-27` `constraint` No endpoint creates an account. `src: User roles para 3`
- [ ] `C-RL-28` `constraint` No path changes the role of an account. `src: User roles para 3`
- [ ] `C-RL-29` `constraint` A planner reaches only their own reservations. `src: User roles para 3`
- [ ] `C-RL-30` `capability` A release aimed at another planner's reservation is rejected. `src: User roles para 3`

## C-CF Core features

- [ ] `C-CF-01` `capability` A planner reserves a whole number of pallets of one item. `src: Core features rule 1`
- [ ] `C-CF-02` `data` `on_hand` stays unchanged when a reservation is accepted. `src: Core features rule 1`
- [ ] `C-CF-03` `data` `reserved` rises by the reserved quantity. `src: Core features rule 1`
- [ ] `C-CF-04` `data` Free stock is `on_hand` minus `reserved`. `src: Core features rule 1`
- [ ] `C-CF-05` `constraint` Free stock is computed on every read. `src: Core features rule 1`
- [ ] `C-CF-06` `constraint` No stored free column exists. `src: Core features rule 1`
- [ ] `C-CF-07` `constraint` No cached free counter exists. `src: Core features rule 1`
- [ ] `C-CF-08` `literal` A reservation whose quantity exceeds free stock is refused with `409`. `src: Core features rule 2`
- [ ] `C-CF-09` `literal` The reservation refusal body carries `free_quantity`. `src: Core features rule 2`
- [ ] `C-CF-10` `data` `free_quantity` is the whole number still free. `src: Core features rule 2`
- [ ] `C-CF-11` `constraint` A refused reservation moves no count. `src: Core features rule 2`
- [ ] `C-CF-12` `constraint` A refused reservation writes no ledger line. `src: Core features rule 2`
- [ ] `C-CF-13` `data` The database refuses a `reserved` value below zero. `src: Core features rule 3`
- [ ] `C-CF-14` `data` The database refuses a `reserved` value above `on_hand`. `src: Core features rule 3`
- [ ] `C-CF-15` `constraint` A reservation moves the counter inside one transaction. `src: Core features rule 3`
- [ ] `C-CF-16` `constraint` A reservation writes the reservation row inside the same transaction. `src: Core features rule 3`
- [ ] `C-CF-17` `constraint` A reservation appends the ledger line inside the same transaction. `src: Core features rule 3`
- [ ] `C-CF-18` `constraint` A reservation locks the item row. `src: Core features rule 3`
- [ ] `C-CF-19` `capability` Two simultaneous reservations for the last pallets leave exactly one success. `src: Core features rule 3`
- [ ] `C-CF-20` `literal` Two simultaneous reservations for the last pallets leave exactly one `409`. `src: Core features rule 3`
- [ ] `C-CF-21` `literal` A quantity below `1` is refused with `422`. `src: Core features rule 4`
- [ ] `C-CF-22` `capability` A planner releases their own `held` reservation by `reference`. `src: Core features rule 5`
- [ ] `C-CF-23` `data` A released reservation carries `status` `released`. `src: Core features rule 5`
- [ ] `C-CF-24` `data` `reserved` falls by the released quantity. `src: Core features rule 5`
- [ ] `C-CF-25` `capability` Free stock returns after a release. `src: Core features rule 5`
- [ ] `C-CF-26` `literal` Releasing a reservation already `released` is refused with `409`. `src: Core features rule 5`
- [ ] `C-CF-27` `capability` A stock admin moves `on_hand` by a signed `delta`. `src: Core features rule 6`
- [ ] `C-CF-28` `constraint` An adjustment carries a written `reason`. `src: Core features rule 6`
- [ ] `C-CF-29` `data` `reserved` never changes on an adjustment. `src: Core features rule 6`
- [ ] `C-CF-30` `literal` An adjustment leaving `on_hand` below `reserved` is refused with `409`. `src: Core features rule 6`
- [ ] `C-CF-31` `data` The adjustment refusal body carries `free_quantity`. `src: Core features rule 6`
- [ ] `C-CF-32` `constraint` `on_hand` is unchanged after a refused adjustment. `src: Core features rule 6`
- [ ] `C-CF-33` `capability` One accepted reservation appends one ledger line. `src: Core features rule 7`
- [ ] `C-CF-34` `capability` One accepted release appends one ledger line. `src: Core features rule 7`
- [ ] `C-CF-35` `capability` One accepted adjustment appends one ledger line. `src: Core features rule 7`
- [ ] `C-CF-36` `data` A ledger line records the item. `src: Core features rule 7`
- [ ] `C-CF-37` `data` A ledger line records `kind`. `src: Core features rule 7`
- [ ] `C-CF-38` `data` A ledger line records the signed `quantity_delta` in free stock. `src: Core features rule 7`
- [ ] `C-CF-39` `data` A ledger line records `free_after`. `src: Core features rule 7`
- [ ] `C-CF-40` `data` A ledger line records the actor. `src: Core features rule 7`
- [ ] `C-CF-41` `data` A ledger line records the time. `src: Core features rule 7`
- [ ] `C-CF-42` `constraint` A refused mutation appends no ledger line. `src: Core features rule 7`
- [ ] `C-CF-43` `constraint` Ledger lines are append-only. `src: Core features rule 8`
- [ ] `C-CF-44` `capability` Releasing a reservation appends a `release` line. `src: Core features rule 8`
- [ ] `C-CF-45` `constraint` Releasing a reservation leaves the `reserve` line standing. `src: Core features rule 8`
- [ ] `C-CF-46` `constraint` No endpoint rewrites a ledger line. `src: Core features rule 8`
- [ ] `C-CF-47` `constraint` No endpoint removes a ledger line. `src: Core features rule 8`
- [ ] `C-CF-48` `capability` The board shows one row per pallet item. `src: Core features rule 9`
- [ ] `C-CF-49` `data` A board row carries the on-hand count. `src: Core features rule 9`
- [ ] `C-CF-50` `data` A board row carries the held count. `src: Core features rule 9`
- [ ] `C-CF-51` `data` A board row carries the free count. `src: Core features rule 9`
- [ ] `C-CF-52` `constraint` Board counts are derived from rows on every read. `src: Core features rule 9`
- [ ] `C-CF-53` `literal` A change made by one signed-in user reaches every other open board within `5` seconds. `src: Core features rule 9`
- [ ] `C-CF-54` `constraint` The board converges with no manual reload. `src: Core features rule 9`
- [ ] `C-CF-55` `ui` Each changed count animates to the new value. `src: Core features rule 9`
- [ ] `C-CF-56` `data` A new reservation opens at `status` `held`. `src: Core features rule 1`

## C-UF User flow

- [ ] `C-UF-01` `contract` `/login` signs a user in from an email address with a password. `src: User flow route table row 1`
- [ ] `C-UF-02` `contract` `/login` needs no authentication. `src: User flow route table row 1`
- [ ] `C-UF-03` `contract` `/board` shows the live allocation board. `src: User flow route table row 2`
- [ ] `C-UF-04` `contract` `/board` opens to any signed-in role. `src: User flow route table row 2`
- [ ] `C-UF-05` `contract` `/board/:sku` shows one item with counts, ledger, action. `src: User flow route table row 3`
- [ ] `C-UF-06` `contract` `/board/:sku` opens to any signed-in role. `src: User flow route table row 3`
- [ ] `C-UF-07` `contract` `/reservations` shows the planner's own reservations. `src: User flow route table row 4`
- [ ] `C-UF-08` `contract` `/reservations` opens to a planner only. `src: User flow route table row 4`
- [ ] `C-UF-09` `contract` `/ledger` shows every movement newest first. `src: User flow route table row 5`
- [ ] `C-UF-10` `contract` `/ledger` opens to any signed-in role. `src: User flow route table row 5`
- [ ] `C-UF-11` `capability` `/` redirects to `/board` for a signed-in user. `src: User flow para 2`
- [ ] `C-UF-12` `capability` `/` redirects to `/login` for an anonymous visitor. `src: User flow para 2`
- [ ] `C-UF-13` `capability` An anonymous visitor at any other route is redirected to `/login`. `src: User flow para 2`
- [ ] `C-UF-14` `capability` A `stock_admin` at `/reservations` is redirected to `/board`. `src: User flow para 2`
- [ ] `C-UF-15` `capability` An `auditor` at `/reservations` is redirected to `/board`. `src: User flow para 2`
- [ ] `C-UF-16` `literal` The reservations API answers `403` whatever the interface did. `src: User flow para 2`
- [ ] `C-UF-17` `ui` A planner signs in as `planner@example.com`. `src: User flow journey 1`
- [ ] `C-UF-18` `ui` The item `PLT-1001` opens with free `18`. `src: User flow journey 1`
- [ ] `C-UF-19` `ui` A reservation of `4` moves free to `14`. `src: User flow journey 1`
- [ ] `C-UF-20` `ui` A reservation of `4` moves held to `10`. `src: User flow journey 1`
- [ ] `C-UF-21` `ui` A `reserve` line appears naming `Dana Ryecroft`. `src: User flow journey 1`
- [ ] `C-UF-22` `ui` The reservations page lists the new hold. `src: User flow journey 2`
- [ ] `C-UF-23` `ui` Releasing the hold moves free back to `18`. `src: User flow journey 2`
- [ ] `C-UF-24` `ui` A `release` line joins the ledger above the `reserve` line. `src: User flow journey 2`
- [ ] `C-UF-25` `ui` The `reserve` line remains after a release. `src: User flow journey 2`
- [ ] `C-UF-26` `ui` A stock admin signs in as `stock_admin@example.com`. `src: User flow journey 3`
- [ ] `C-UF-27` `ui` An adjustment of `+5` on `PLT-1004` moves on-hand to `15`. `src: User flow journey 3`
- [ ] `C-UF-28` `ui` An adjustment of `+5` on `PLT-1004` moves free to `15`. `src: User flow journey 3`
- [ ] `C-UF-29` `ui` An `adjust` line carries the reason. `src: User flow journey 3`
- [ ] `C-UF-30` `ui` A planner asking for `1` of `PLT-1002` reads that `0` are free. `src: User flow journey 4`
- [ ] `C-UF-31` `ui` The reserve control stays in place after a refusal. `src: User flow journey 4`
- [ ] `C-UF-32` `ui` Nothing moves on the board after a refused reservation. `src: User flow journey 4`
- [ ] `C-UF-33` `ui` No ledger line appears after a refused reservation. `src: User flow journey 4`
- [ ] `C-UF-34` `ui` A reservation of `2` on `PLT-1003` moves a second browser free count from `8` to `6`. `src: User flow journey 5`
- [ ] `C-UF-35` `ui` The second browser board moves untouched within `5` seconds. `src: User flow journey 5`
- [ ] `C-UF-36` `ui` Every page carries a loading state. `src: User flow states`
- [ ] `C-UF-37` `ui` A failed request leaves the page standing with a retry. `src: User flow states`
- [ ] `C-UF-38` `ui` `PLT-1005` reads three zeros. `src: User flow states`
- [ ] `C-UF-39` `ui` `PLT-1005` carries a short line saying nothing has moved yet. `src: User flow states`
- [ ] `C-UF-40` `ui` The zero item never reads as an error. `src: User flow states`
- [ ] `C-UF-41` `ui` A planner holding nothing sees a short line. `src: User flow states`
- [ ] `C-UF-42` `ui` A planner holding nothing never sees a blank panel. `src: User flow states`

## C-UX UI and UX notes

- [ ] `C-UX-01` `ui` The interface reads industrial, dense, high contrast. `src: UI/UX notes para 1`
- [ ] `C-UX-02` `ui` The interface is a control surface read at distance. `src: UI/UX notes para 1`
- [ ] `C-UX-03` `literal` The background colour is `#0F1211`. `src: UI/UX notes palette`
- [ ] `C-UX-04` `literal` The surface colour is `#171B1A`. `src: UI/UX notes palette`
- [ ] `C-UX-05` `literal` The text colour is `#E8EDEB`. `src: UI/UX notes palette`
- [ ] `C-UX-06` `literal` The muted colour is `#8A9491`. `src: UI/UX notes palette`
- [ ] `C-UX-07` `literal` The primary colour is `#2FA37A`. `src: UI/UX notes palette`
- [ ] `C-UX-08` `literal` The primary hover colour is `#248260`. `src: UI/UX notes palette`
- [ ] `C-UX-09` `literal` The border colour is `#2A3230`. `src: UI/UX notes palette`
- [ ] `C-UX-10` `literal` The held-stock colour is `#C2833B`. `src: UI/UX notes palette`
- [ ] `C-UX-11` `literal` The refused or zero-free colour is `#D4525F`. `src: UI/UX notes palette`
- [ ] `C-UX-12` `ui` Green marks free stock only. `src: UI/UX notes palette`
- [ ] `C-UX-13` `ui` Amber marks held stock. `src: UI/UX notes palette`
- [ ] `C-UX-14` `literal` Prose is set in `"IBM Plex Sans", system-ui, sans-serif`. `src: UI/UX notes type`
- [ ] `C-UX-15` `literal` Quantities are set in `"IBM Plex Mono", ui-monospace, monospace`. `src: UI/UX notes type`
- [ ] `C-UX-16` `ui` Every sku is set in the monospace face. `src: UI/UX notes type`
- [ ] `C-UX-17` `ui` Every reference is set in the monospace face. `src: UI/UX notes type`
- [ ] `C-UX-18` `literal` The page title is set at `30/38`. `src: UI/UX notes type`
- [ ] `C-UX-19` `literal` The section heading is set at `20/28`. `src: UI/UX notes type`
- [ ] `C-UX-20` `literal` The body size is set at `15/22`. `src: UI/UX notes type`
- [ ] `C-UX-21` `literal` The meta size is set at `12/18`. `src: UI/UX notes type`
- [ ] `C-UX-22` `literal` The free-count numeral is set at `40/44`. `src: UI/UX notes type`
- [ ] `C-UX-23` `ui` The free-count numeral uses tabular numerals. `src: UI/UX notes type`
- [ ] `C-UX-24` `ui` The free-count numeral is the largest element on a board row. `src: UI/UX notes type`
- [ ] `C-UX-25` `literal` Cards carry a `10px` radius. `src: UI/UX notes shape`
- [ ] `C-UX-26` `literal` Buttons carry a `6px` radius. `src: UI/UX notes shape`
- [ ] `C-UX-27` `literal` Count chips carry a `999px` pill radius. `src: UI/UX notes shape`
- [ ] `C-UX-28` `literal` Borders are hairline at `1px`. `src: UI/UX notes shape`
- [ ] `C-UX-29` `ui` A shadow is never used for separation. `src: UI/UX notes shape`
- [ ] `C-UX-30` `literal` Card padding is `20px`. `src: UI/UX notes shape`
- [ ] `C-UX-31` `literal` The spacing step is `8px`. `src: UI/UX notes shape`
- [ ] `C-UX-32` `literal` Board rows sit on a `56px` grid. `src: UI/UX notes shape`
- [ ] `C-UX-33` `literal` Hover uses a `150ms` duration. `src: UI/UX notes motion`
- [ ] `C-UX-34` `literal` Focus uses a `150ms` duration. `src: UI/UX notes motion`
- [ ] `C-UX-35` `literal` A count change uses a `250ms` duration. `src: UI/UX notes motion`
- [ ] `C-UX-36` `literal` Motion easing is `ease-out`. `src: UI/UX notes motion`
- [ ] `C-UX-37` `ui` A changed count counts to the new value rather than snapping. `src: UI/UX notes motion`
- [ ] `C-UX-38` `ui` The row of a changed count briefly highlights. `src: UI/UX notes motion`
- [ ] `C-UX-39` `literal` Under `prefers-reduced-motion: reduce` every transition drops to `0ms`. `src: UI/UX notes motion`
- [ ] `C-UX-40` `ui` A board row leads with the sku. `src: UI/UX notes board row`
- [ ] `C-UX-41` `ui` A board row carries the item name after the sku. `src: UI/UX notes board row`
- [ ] `C-UX-42` `ui` A board row carries three chips in the fixed order on hand, held, free. `src: UI/UX notes board row`
- [ ] `C-UX-43` `ui` Each chip carries a text label alongside colour. `src: UI/UX notes board row`
- [ ] `C-UX-44` `ui` The refusal sits beside the control that produced the refusal. `src: UI/UX notes refusal`
- [ ] `C-UX-45` `ui` The refusal states the quantity still free as a number. `src: UI/UX notes refusal`
- [ ] `C-UX-46` `ui` The refusal persists until the planner acts. `src: UI/UX notes refusal`
- [ ] `C-UX-47` `ui` The refusal is never a toast that vanishes. `src: UI/UX notes refusal`
- [ ] `C-UX-48` `literal` Breakpoints sit at `640px`, `768px`, `1024px`. `src: UI/UX notes responsive`
- [ ] `C-UX-49` `ui` The layout drops to one column below the smallest breakpoint. `src: UI/UX notes responsive`
- [ ] `C-UX-50` `literal` Touch targets are `44x44px`. `src: UI/UX notes responsive`
- [ ] `C-UX-51` `ui` All text meets WCAG AA contrast. `src: UI/UX notes responsive`
- [ ] `C-UX-52` `ui` The interface supports full keyboard navigation. `src: UI/UX notes responsive`
- [ ] `C-UX-53` `literal` The focus ring is visible at `2px`. `src: UI/UX notes responsive`
- [ ] `C-UX-54` `ui` Count changes are announced in a polite live region. `src: UI/UX notes responsive`

## C-CN Constraints

- [ ] `C-CN-01` `constraint` Stock enters only through an admin adjustment. `src: Constraints bullet 1`
- [ ] `C-CN-02` `constraint` Stock leaves only through an admin adjustment. `src: Constraints bullet 1`
- [ ] `C-CN-03` `constraint` A correction is a new adjustment in the opposite direction. `src: Constraints bullet 5`

## C-TR Technical requirements

- [ ] `C-TR-01` `data` The database refuses a `reserved` value that rises above `on_hand`. `src: Technical requirements concurrency`
- [ ] `C-TR-02` `constraint` A reservation takes the item row with a row lock. `src: Technical requirements concurrency`
- [ ] `C-TR-03` `constraint` A release takes the item row with a row lock. `src: Technical requirements concurrency`
- [ ] `C-TR-04` `constraint` An adjustment takes the item row with a row lock. `src: Technical requirements concurrency`
- [ ] `C-TR-05` `constraint` The counter move, the reservation write, the ledger append share one transaction. `src: Technical requirements concurrency`
- [ ] `C-TR-06` `literal` A constraint violation is answered `409` carrying `free_quantity`. `src: Technical requirements concurrency`
- [ ] `C-TR-07` `constraint` A constraint violation never surfaces as a `500`. `src: Technical requirements concurrency`
- [ ] `C-TR-08` `constraint` A free-stock decision made only in application code is a defect. `src: Technical requirements concurrency`
- [ ] `C-TR-09` `literal` The board converges across clients within `5` seconds of a change. `src: Technical requirements live board`
- [ ] `C-TR-10` `constraint` Board convergence happens without a manual reload. `src: Technical requirements live board`
- [ ] `C-TR-11` `constraint` A polling refresh satisfies the convergence requirement. `src: Technical requirements live board`
- [ ] `C-TR-12` `constraint` A same-origin server-sent event stream satisfies the convergence requirement. `src: Technical requirements live board`
- [ ] `C-TR-13` `constraint` No external broker is introduced. `src: Technical requirements live board`
- [ ] `C-TR-14` `literal` `GET /api/health` answers `200` once the database answers. `src: Technical requirements bullet 5`
- [ ] `C-TR-15` `contract` Login returns the token as `access_token`. `src: Technical requirements bullet 4`
- [ ] `C-TR-16` `contract` The client sends the token in an `Authorization` header with the `Bearer` scheme. `src: Technical requirements bullet 4`
- [ ] `C-TR-17` `literal` PostgreSQL is reachable at `DATABASE_URL`. `src: Technical requirements postgresql`
- [ ] `C-TR-18` `constraint` The table names are an interface rather than an implementation detail. `src: Technical requirements postgresql`
- [ ] `C-TR-19` `constraint` The column names are an interface rather than an implementation detail. `src: Technical requirements postgresql`

## C-DM Data model

- [ ] `C-DM-01` `data` `users` carries `id`. `src: Data model users`
- [ ] `C-DM-02` `data` `users` carries a unique indexed `email`. `src: Data model users`
- [ ] `C-DM-03` `data` `users` carries a password hash. `src: Data model users`
- [ ] `C-DM-04` `data` `users` carries `role`. `src: Data model users`
- [ ] `C-DM-05` `literal` A `role` is one of `planner`, `stock_admin`, `auditor`. `src: Data model users`
- [ ] `C-DM-06` `data` `users` carries `name`. `src: Data model users`
- [ ] `C-DM-07` `data` `users` carries a created timestamp. `src: Data model users`
- [ ] `C-DM-08` `data` `stock_items` carries `id`. `src: Data model stock items`
- [ ] `C-DM-09` `data` `stock_items` carries a unique indexed `sku`. `src: Data model stock items`
- [ ] `C-DM-10` `literal` A `sku` is the string `PLT-` followed by four digits. `src: Data model stock items`
- [ ] `C-DM-11` `data` `stock_items` carries `name`. `src: Data model stock items`
- [ ] `C-DM-12` `data` `stock_items` carries `on_hand` as an integer. `src: Data model stock items`
- [ ] `C-DM-13` `constraint` `on_hand` never falls below zero. `src: Data model stock items`
- [ ] `C-DM-14` `data` `stock_items` carries `reserved` as an integer. `src: Data model stock items`
- [ ] `C-DM-15` `constraint` `reserved` never falls below zero. `src: Data model stock items`
- [ ] `C-DM-16` `constraint` `reserved` never rises above `on_hand`. `src: Data model stock items`
- [ ] `C-DM-17` `data` `stock_items` carries created, updated timestamps. `src: Data model stock items`
- [ ] `C-DM-18` `constraint` Free stock is never stored. `src: Data model stock items`
- [ ] `C-DM-19` `data` `reservations` carries `id`. `src: Data model reservations`
- [ ] `C-DM-20` `data` `reservations` carries a unique indexed `reference`. `src: Data model reservations`
- [ ] `C-DM-21` `literal` A `reference` is the string `RSV-` followed by four digits. `src: Data model reservations`
- [ ] `C-DM-22` `data` `reservations` carries `stock_item_id` referencing `stock_items`. `src: Data model reservations`
- [ ] `C-DM-23` `data` `reservations` carries `planner_id` referencing `users`. `src: Data model reservations`
- [ ] `C-DM-24` `data` `reservations` carries `quantity` as an integer. `src: Data model reservations`
- [ ] `C-DM-25` `literal` A reservation `quantity` is at least `1`. `src: Data model reservations`
- [ ] `C-DM-26` `data` `reservations` carries `status`. `src: Data model reservations`
- [ ] `C-DM-27` `literal` A reservation `status` is one of `held` or `released`. `src: Data model reservations`
- [ ] `C-DM-28` `data` `reservations` carries created, released timestamps. `src: Data model reservations`
- [ ] `C-DM-29` `constraint` Every route naming a reservation names the `reference`. `src: Data model reservations`
- [ ] `C-DM-30` `constraint` No route names a reservation by database id. `src: Data model reservations`
- [ ] `C-DM-31` `data` `reserved` equals the sum of `quantity` over an item's `held` reservations. `src: Data model reservations`
- [ ] `C-DM-32` `data` `ledger_entries` carries `id`. `src: Data model ledger entries`
- [ ] `C-DM-33` `data` `ledger_entries` carries `stock_item_id` referencing `stock_items`. `src: Data model ledger entries`
- [ ] `C-DM-34` `data` `ledger_entries` carries `reservation_id` referencing `reservations`. `src: Data model ledger entries`
- [ ] `C-DM-35` `data` `reservation_id` is null on an adjustment. `src: Data model ledger entries`
- [ ] `C-DM-36` `data` `ledger_entries` carries `kind`. `src: Data model ledger entries`
- [ ] `C-DM-37` `literal` A `kind` is one of `reserve`, `release`, `adjust`. `src: Data model ledger entries`
- [ ] `C-DM-38` `data` `ledger_entries` carries `quantity_delta` as the signed change in free stock. `src: Data model ledger entries`
- [ ] `C-DM-39` `data` `ledger_entries` carries `free_after`. `src: Data model ledger entries`
- [ ] `C-DM-40` `data` `ledger_entries` carries `actor_id` referencing `users`. `src: Data model ledger entries`
- [ ] `C-DM-41` `data` `ledger_entries` carries `reason`. `src: Data model ledger entries`
- [ ] `C-DM-42` `data` `reason` is null except on an adjustment. `src: Data model ledger entries`
- [ ] `C-DM-43` `data` `ledger_entries` carries a created timestamp. `src: Data model ledger entries`
- [ ] `C-DM-44` `data` `quantity_delta` is minus the quantity on a `reserve` line. `src: Data model ledger entries`
- [ ] `C-DM-45` `data` `quantity_delta` is plus the quantity on a `release` line. `src: Data model ledger entries`
- [ ] `C-DM-46` `data` `quantity_delta` is the admin delta on an `adjust` line. `src: Data model ledger entries`
- [ ] `C-DM-47` `literal` The seeded password is `deku-demo-pw-2026`. `src: Data model para 2`
- [ ] `C-DM-48` `constraint` The seeded password literal works at login. `src: Data model para 2`
- [ ] `C-DM-49` `constraint` The seeded password is written into the app readme. `src: Data model para 2`
- [ ] `C-DM-50` `constraint` Seeding is deterministic. `src: Data model seed data`
- [ ] `C-DM-51` `constraint` Seeding is idempotent, keyed on `email`, `sku`, `reference`. `src: Data model seed data`
- [ ] `C-DM-52` `constraint` Restarting duplicates no row. `src: Data model seed data`
- [ ] `C-DM-53` `constraint` Restarting re-appends no ledger line. `src: Data model seed data`
- [ ] `C-DM-54` `literal` `planner@example.com` is a `planner` named `Dana Ryecroft`. `src: Data model seed data`
- [ ] `C-DM-55` `literal` `planner2@example.com` is a `planner` named `Marek Toll`. `src: Data model seed data`
- [ ] `C-DM-56` `literal` `stock_admin@example.com` is the `stock_admin` named `Ivo Bell`. `src: Data model seed data`
- [ ] `C-DM-57` `literal` `auditor@example.com` is the `auditor` named `Sofia Crane`. `src: Data model seed data`
- [ ] `C-DM-58` `literal` `PLT-1001` is `Oak Pallet Standard` at `on_hand` `24`. `src: Data model seed data`
- [ ] `C-DM-59` `literal` `PLT-1001` opens at `reserved` `6`. `src: Data model seed data`
- [ ] `C-DM-60` `literal` `PLT-1002` is `Steel Cage Pallet` at `on_hand` `12`. `src: Data model seed data`
- [ ] `C-DM-61` `literal` `PLT-1002` opens at `reserved` `12`. `src: Data model seed data`
- [ ] `C-DM-62` `literal` `PLT-1003` is `Euro Pallet Light` at `on_hand` `8`. `src: Data model seed data`
- [ ] `C-DM-63` `literal` `PLT-1003` opens at `reserved` `0`. `src: Data model seed data`
- [ ] `C-DM-64` `literal` `PLT-1004` is `Chill Pallet Insulated` at `on_hand` `10`. `src: Data model seed data`
- [ ] `C-DM-65` `literal` `PLT-1004` opens at `reserved` `0`. `src: Data model seed data`
- [ ] `C-DM-66` `literal` `PLT-1005` is `Drum Cradle Pallet` at `on_hand` `0`. `src: Data model seed data`
- [ ] `C-DM-67` `literal` `PLT-1005` opens at `reserved` `0`. `src: Data model seed data`
- [ ] `C-DM-68` `literal` `RSV-1001` holds `6` of `PLT-1001` for `planner@example.com`. `src: Data model seed data`
- [ ] `C-DM-69` `literal` `RSV-1002` holds `12` of `PLT-1002` for `planner2@example.com`. `src: Data model seed data`
- [ ] `C-DM-70` `data` The seed writes two opening `reserve` ledger lines. `src: Data model seed data`
- [ ] `C-DM-71` `constraint` The ledger reconciles with `reserved` before any further movement. `src: Data model seed data`
- [ ] `C-DM-72` `data` `PLT-1003` opens with no ledger line. `src: Data model seed data`
- [ ] `C-DM-73` `data` `PLT-1004` opens with no ledger line. `src: Data model seed data`
- [ ] `C-DM-74` `data` `PLT-1005` opens with no ledger line. `src: Data model seed data`
- [ ] `C-DM-75` `literal` New references continue from `RSV-1003`. `src: Data model seed data`

## C-BP Build plan

- [ ] `C-BP-01` `contract` The application serves one origin. `src: Build plan step 1`
- [ ] `C-BP-02` `contract` The port comes from `APP_PUBLIC_PORT`. `src: Build plan step 1`
- [ ] `C-BP-03` `contract` The server binds `0.0.0.0`. `src: Build plan step 1`
- [ ] `C-BP-04` `contract` A production build sits behind a preview server. `src: Build plan step 1`
- [ ] `C-BP-05` `capability` Migrations create the four tables. `src: Build plan step 2`
- [ ] `C-BP-06` `capability` The check constraint lands with the migrations. `src: Build plan step 2`
- [ ] `C-BP-07` `capability` The unique indexes land with the migrations. `src: Build plan step 2`
- [ ] `C-BP-08` `constraint` Running the seed twice leaves the row counts unchanged. `src: Build plan step 2`
- [ ] `C-BP-09` `capability` Login, bearer middleware, the three role checks land together. `src: Build plan step 3`
- [ ] `C-BP-10` `capability` The board, the ledger, a planner's own reservations all compute free stock from rows. `src: Build plan step 4`
- [ ] `C-BP-11` `capability` The locked transaction lands before the interface. `src: Build plan step 5`
- [ ] `C-BP-12` `capability` The adjustment reuses the same lock. `src: Build plan step 6`
- [ ] `C-BP-13` `capability` The interface lands after the reservation route. `src: Build plan step 7`
- [ ] `C-BP-14` `capability` Board refresh arrives by interval or same-origin event stream. `src: Build plan step 8`
- [ ] `C-BP-15` `capability` The server is started to outlive the session. `src: Build plan step 9`
- [ ] `C-BP-16` `capability` The listening process is confirmed after detaching. `src: Build plan step 9`

## C-DC Deployment contract

- [ ] `C-DC-01` `contract` The app is reachable at `APP_PUBLIC_URL`. `src: Deployment contract bullet 1`
- [ ] `C-DC-02` `literal` The port mapping is `${APP_PUBLIC_PORT}:4173`. `src: Deployment contract bullet 1`
- [ ] `C-DC-03` `literal` `4173` is the container-internal port. `src: Deployment contract bullet 1`
- [ ] `C-DC-04` `contract` Neither port is hardcoded. `src: Deployment contract bullet 1`
- [ ] `C-DC-05` `contract` The HTTP API is served on the same origin under the `/api` prefix. `src: Deployment contract bullet 2`
- [ ] `C-DC-06` `literal` `GET /api/health` returns `200` once the app is ready. `src: Deployment contract bullet 3`
- [ ] `C-DC-07` `contract` The app starts from the environment image with no manual steps. `src: Deployment contract bullet 4`
- [ ] `C-DC-08` `contract` Login credentials are written to the app readme. `src: Deployment contract bullet 5`
- [ ] `C-DC-09` `contract` The server outlives the session. `src: Deployment contract bullet 8`
- [ ] `C-DC-10` `contract` Grading runs after the session ends. `src: Deployment contract bullet 8`
- [ ] `C-DC-11` `contract` The listener never binds `127.0.0.1`. `src: Deployment contract bullet 9`
- [ ] `C-DC-12` `contract` The listener never binds `localhost`. `src: Deployment contract bullet 9`
- [ ] `C-DC-13` `contract` The backing service named in the brief is already running. `src: Deployment contract bullet 12`
- [ ] `C-DC-14` `literal` `POST /api/auth/login` takes an `email` with a `password`. `src: Deployment contract api shapes`
- [ ] `C-DC-15` `literal` `POST /api/auth/login` returns `200` carrying `access_token`. `src: Deployment contract api shapes`
- [ ] `C-DC-16` `literal` `GET /api/board` returns `200` carrying an array of board rows. `src: Deployment contract api shapes`
- [ ] `C-DC-17` `literal` A board row carries `sku`, `name`, `on_hand`, `reserved`, `free`. `src: Deployment contract api shapes`
- [ ] `C-DC-18` `literal` `GET /api/reservations` returns `200` for a planner. `src: Deployment contract api shapes`
- [ ] `C-DC-19` `literal` `GET /api/reservations` returns `403` for another role. `src: Deployment contract api shapes`
- [ ] `C-DC-20` `literal` A listed reservation carries `reference`, `sku`, `quantity`, `status`. `src: Deployment contract api shapes`
- [ ] `C-DC-21` `literal` `POST /api/reservations` takes a `sku` with a `quantity`. `src: Deployment contract api shapes`
- [ ] `C-DC-22` `literal` `POST /api/reservations` returns `200` or `201` on success. `src: Deployment contract api shapes`
- [ ] `C-DC-23` `literal` `POST /api/reservations` returns `409` over free stock. `src: Deployment contract api shapes`
- [ ] `C-DC-24` `literal` `POST /api/reservations` returns `422` below `1`. `src: Deployment contract api shapes`
- [ ] `C-DC-25` `literal` `POST /api/reservations` returns `403` for another role. `src: Deployment contract api shapes`
- [ ] `C-DC-26` `literal` A created reservation carries `reference`, `sku`, `quantity`, `status`, `free_after`. `src: Deployment contract api shapes`
- [ ] `C-DC-27` `literal` `POST /api/reservations/{reference}/release` returns `200` for the owning planner. `src: Deployment contract api shapes`
- [ ] `C-DC-28` `literal` `POST /api/reservations/{reference}/release` returns `409` when already released. `src: Deployment contract api shapes`
- [ ] `C-DC-29` `literal` `POST /api/reservations/{reference}/release` returns `403` for another planner. `src: Deployment contract api shapes`
- [ ] `C-DC-30` `literal` A released reservation carries `reference`, `status`, `free_after`. `src: Deployment contract api shapes`
- [ ] `C-DC-31` `literal` `POST /api/adjustments` takes a `sku`, a `delta`, a `reason`. `src: Deployment contract api shapes`
- [ ] `C-DC-32` `literal` `POST /api/adjustments` returns `200` or `201` on success. `src: Deployment contract api shapes`
- [ ] `C-DC-33` `literal` `POST /api/adjustments` returns `409` below held stock. `src: Deployment contract api shapes`
- [ ] `C-DC-34` `literal` `POST /api/adjustments` returns `403` for another role. `src: Deployment contract api shapes`
- [ ] `C-DC-35` `literal` An adjustment result carries `sku`, `on_hand`, `reserved`, `free`, `delta`. `src: Deployment contract api shapes`
- [ ] `C-DC-36` `literal` `GET /api/ledger` takes an optional `sku` query parameter. `src: Deployment contract api shapes`
- [ ] `C-DC-37` `literal` `GET /api/ledger` returns `200` carrying an array newest first. `src: Deployment contract api shapes`
- [ ] `C-DC-38` `literal` A ledger row carries `sku`, `kind`, `quantity_delta`, `free_after`, `actor_email`, `created_at`. `src: Deployment contract api shapes`
- [ ] `C-DC-39` `literal` Every endpoint outside login, health requires a valid bearer token. `src: Deployment contract rules`
- [ ] `C-DC-40` `literal` An anonymous call to a protected endpoint is rejected with `401`. `src: Deployment contract rules`
- [ ] `C-DC-41` `literal` Both stock refusals return `409` carrying `free_quantity`. `src: Deployment contract rules`
- [ ] `C-DC-42` `constraint` A refusal body names the reason. `src: Deployment contract rules`
- [ ] `C-DC-43` `literal` An unknown `sku` is answered `404`. `src: Deployment contract rules`
- [ ] `C-DC-44` `constraint` A business-rule violation returns a `4xx` with a message. `src: Deployment contract rules`
- [ ] `C-DC-45` `constraint` A refused mutation never returns a `200`. `src: Deployment contract rules`
- [ ] `C-DC-46` `constraint` The API never returns a `5xx`. `src: Deployment contract rules`
- [ ] `C-DC-47` `constraint` A database constraint stands behind the free-stock decision. `src: Deployment contract no shortcuts`
- [ ] `C-DC-48` `constraint` No cached counter feeds the board. `src: Deployment contract no shortcuts`
- [ ] `C-DC-49` `constraint` The board derives every count from `on_hand` with `reserved`. `src: Deployment contract no shortcuts`
- [ ] `C-DC-50` `constraint` No ledger line for an accepted mutation is omitted. `src: Deployment contract no shortcuts`
- [ ] `C-DC-51` `ui` The interface never explains how the enforcement works. `src: Deployment contract no shortcuts`

## Pinned literals

| Value | What it is | Item | Stated in |
|---|---|---|---|
| `0` | free stock at the floor | C-OV-14 | Overview para 3 |
| `planner` | role that reserves stock | C-RL-25 | User roles para 2 |
| `stock_admin` | role that adjusts on-hand counts | C-RL-25 | User roles para 2 |
| `401` | unauthenticated status | C-RL-25 | User roles para 2 |
| `403` | forbidden status | C-RL-25 | User roles para 2 |
| `409` | stock refusal status | C-CF-08 | Core features rule 2 |
| `free_quantity` | refusal body field naming the stock still free | C-CF-09 | Core features rule 2 |
| `1` | the smallest legal reservation quantity | C-CF-21 | Core features rule 4 |
| `422` | quantity validation status | C-CF-21 | Core features rule 4 |
| `released` | reservation status after a release | C-CF-26 | Core features rule 5 |
| `on_hand` | graded value the brief pins | C-CF-30 | Core features rule 6 |
| `reserved` | graded value the brief pins | C-CF-30 | Core features rule 6 |
| `5` | seconds inside which every open board converges | C-CF-53 | Core features rule 9 |
| `#0F1211` | graded value the brief pins | C-UX-03 | UI/UX notes palette |
| `#171B1A` | graded value the brief pins | C-UX-04 | UI/UX notes palette |
| `#E8EDEB` | graded value the brief pins | C-UX-05 | UI/UX notes palette |
| `#8A9491` | graded value the brief pins | C-UX-06 | UI/UX notes palette |
| `#2FA37A` | graded value the brief pins | C-UX-07 | UI/UX notes palette |
| `#248260` | graded value the brief pins | C-UX-08 | UI/UX notes palette |
| `#2A3230` | graded value the brief pins | C-UX-09 | UI/UX notes palette |
| `#C2833B` | graded value the brief pins | C-UX-10 | UI/UX notes palette |
| `#D4525F` | graded value the brief pins | C-UX-11 | UI/UX notes palette |
| `"IBM Plex Sans", system-ui, sans-serif` | graded value the brief pins | C-UX-14 | UI/UX notes type |
| `"IBM Plex Mono", ui-monospace, monospace` | graded value the brief pins | C-UX-15 | UI/UX notes type |
| `30/38` | graded value the brief pins | C-UX-18 | UI/UX notes type |
| `20/28` | graded value the brief pins | C-UX-19 | UI/UX notes type |
| `15/22` | graded value the brief pins | C-UX-20 | UI/UX notes type |
| `12/18` | graded value the brief pins | C-UX-21 | UI/UX notes type |
| `40/44` | graded value the brief pins | C-UX-22 | UI/UX notes type |
| `10px` | graded value the brief pins | C-UX-25 | UI/UX notes shape |
| `6px` | graded value the brief pins | C-UX-26 | UI/UX notes shape |
| `999px` | graded value the brief pins | C-UX-27 | UI/UX notes shape |
| `1px` | graded value the brief pins | C-UX-28 | UI/UX notes shape |
| `20px` | graded value the brief pins | C-UX-30 | UI/UX notes shape |
| `8px` | graded value the brief pins | C-UX-31 | UI/UX notes shape |
| `56px` | graded value the brief pins | C-UX-32 | UI/UX notes shape |
| `150ms` | graded value the brief pins | C-UX-33 | UI/UX notes motion |
| `250ms` | graded value the brief pins | C-UX-35 | UI/UX notes motion |
| `ease-out` | graded value the brief pins | C-UX-36 | UI/UX notes motion |
| `prefers-reduced-motion: reduce` | graded value the brief pins | C-UX-39 | UI/UX notes motion |
| `0ms` | graded value the brief pins | C-UX-39 | UI/UX notes motion |
| `640px` | graded value the brief pins | C-UX-48 | UI/UX notes responsive |
| `768px` | graded value the brief pins | C-UX-48 | UI/UX notes responsive |
| `1024px` | graded value the brief pins | C-UX-48 | UI/UX notes responsive |
| `44x44px` | graded value the brief pins | C-UX-50 | UI/UX notes responsive |
| `2px` | graded value the brief pins | C-UX-53 | UI/UX notes responsive |
| `GET /api/health` | graded value the brief pins | C-TR-14 | Technical requirements bullet 5 |
| `200` | success status | C-TR-14 | Technical requirements bullet 5 |
| `DATABASE_URL` | graded value the brief pins | C-TR-17 | Technical requirements postgresql |
| `role` | graded value the brief pins | C-DM-05 | Data model users |
| `auditor` | read-only role | C-DM-05 | Data model users |
| `sku` | graded value the brief pins | C-DM-10 | Data model stock items |
| `PLT-` | graded value the brief pins | C-DM-10 | Data model stock items |
| `reference` | public handle of a reservation | C-DM-21 | Data model reservations |
| `RSV-` | graded value the brief pins | C-DM-21 | Data model reservations |
| `quantity` | graded value the brief pins | C-DM-25 | Data model reservations |
| `status` | graded value the brief pins | C-DM-27 | Data model reservations |
| `held` | reservation status while stock is committed | C-DM-27 | Data model reservations |
| `kind` | graded value the brief pins | C-DM-37 | Data model ledger entries |
| `reserve` | ledger kind for a reservation | C-DM-37 | Data model ledger entries |
| `release` | ledger kind for a release | C-DM-37 | Data model ledger entries |
| `adjust` | ledger kind for an adjustment | C-DM-37 | Data model ledger entries |
| `deku-demo-pw-2026` | password on every seeded account | C-DM-47 | Data model para 2 |
| `planner@example.com` | graded value the brief pins | C-DM-54 | Data model seed data |
| `Dana Ryecroft` | graded value the brief pins | C-DM-54 | Data model seed data |
| `planner2@example.com` | graded value the brief pins | C-DM-55 | Data model seed data |
| `Marek Toll` | graded value the brief pins | C-DM-55 | Data model seed data |
| `stock_admin@example.com` | graded value the brief pins | C-DM-56 | Data model seed data |
| `Ivo Bell` | graded value the brief pins | C-DM-56 | Data model seed data |
| `auditor@example.com` | graded value the brief pins | C-DM-57 | Data model seed data |
| `Sofia Crane` | graded value the brief pins | C-DM-57 | Data model seed data |
| `PLT-1001` | graded value the brief pins | C-DM-58 | Data model seed data |
| `Oak Pallet Standard` | graded value the brief pins | C-DM-58 | Data model seed data |
| `24` | graded value the brief pins | C-DM-58 | Data model seed data |
| `6` | graded value the brief pins | C-DM-59 | Data model seed data |
| `PLT-1002` | graded value the brief pins | C-DM-60 | Data model seed data |
| `Steel Cage Pallet` | graded value the brief pins | C-DM-60 | Data model seed data |
| `12` | graded value the brief pins | C-DM-60 | Data model seed data |
| `PLT-1003` | graded value the brief pins | C-DM-62 | Data model seed data |
| `Euro Pallet Light` | graded value the brief pins | C-DM-62 | Data model seed data |
| `8` | graded value the brief pins | C-DM-62 | Data model seed data |
| `PLT-1004` | graded value the brief pins | C-DM-64 | Data model seed data |
| `Chill Pallet Insulated` | graded value the brief pins | C-DM-64 | Data model seed data |
| `10` | graded value the brief pins | C-DM-64 | Data model seed data |
| `PLT-1005` | graded value the brief pins | C-DM-66 | Data model seed data |
| `Drum Cradle Pallet` | graded value the brief pins | C-DM-66 | Data model seed data |
| `RSV-1001` | graded value the brief pins | C-DM-68 | Data model seed data |
| `RSV-1002` | graded value the brief pins | C-DM-69 | Data model seed data |
| `RSV-1003` | graded value the brief pins | C-DM-75 | Data model seed data |
| `${APP_PUBLIC_PORT}:4173` | graded value the brief pins | C-DC-02 | Deployment contract bullet 1 |
| `4173` | container-internal port | C-DC-03 | Deployment contract bullet 1 |
| `POST /api/auth/login` | graded value the brief pins | C-DC-14 | Deployment contract api shapes |
| `email` | graded value the brief pins | C-DC-14 | Deployment contract api shapes |
| `password` | graded value the brief pins | C-DC-14 | Deployment contract api shapes |
| `access_token` | graded value the brief pins | C-DC-15 | Deployment contract api shapes |
| `GET /api/board` | graded value the brief pins | C-DC-16 | Deployment contract api shapes |
| `name` | graded value the brief pins | C-DC-17 | Deployment contract api shapes |
| `free` | graded value the brief pins | C-DC-17 | Deployment contract api shapes |
| `GET /api/reservations` | graded value the brief pins | C-DC-18 | Deployment contract api shapes |
| `POST /api/reservations` | graded value the brief pins | C-DC-21 | Deployment contract api shapes |
| `201` | created status | C-DC-22 | Deployment contract api shapes |
| `free_after` | graded value the brief pins | C-DC-26 | Deployment contract api shapes |
| `POST /api/reservations/{reference}/release` | graded value the brief pins | C-DC-27 | Deployment contract api shapes |
| `POST /api/adjustments` | graded value the brief pins | C-DC-31 | Deployment contract api shapes |
| `delta` | graded value the brief pins | C-DC-31 | Deployment contract api shapes |
| `reason` | graded value the brief pins | C-DC-31 | Deployment contract api shapes |
| `GET /api/ledger` | graded value the brief pins | C-DC-36 | Deployment contract api shapes |
| `quantity_delta` | graded value the brief pins | C-DC-38 | Deployment contract api shapes |
| `actor_email` | graded value the brief pins | C-DC-38 | Deployment contract api shapes |
| `created_at` | graded value the brief pins | C-DC-38 | Deployment contract api shapes |
| `404` | unknown sku status | C-DC-43 | Deployment contract rules |

### Referenced but not pinned

| What the instruction calls it | Item | Why no literal is pinned |
|---|---|---|
| The wording of an adjustment `reason` | C-CF-28 | the brief requires a written reason without pinning any text, so no grader may match one |
| The display `name` shown beside a ledger line for accounts beyond the seed | C-UF-21 | only the four seeded display names are pinned |
| The refresh interval behind board convergence | C-TR-09 | the brief pins the five-second observable, deliberately leaving transport free |

## Coverage ledger

| Section | Obligation-bearing sentences | Items produced | Held out as ungraded |
|---|---|---|---|
| Overview | 12 | 16 | 0 |
| User roles | 16 | 30 | 0 |
| Core features | 38 | 56 | 0 |
| User flow | 24 | 42 | 0 |
| UI and UX notes | 33 | 54 | 0 |
| Constraints | 3 | 3 | 21 |
| Technical requirements | 19 | 19 | 26 |
| Data model | 44 | 75 | 4 |
| Build plan | 12 | 16 | 0 |
| Deployment contract | 41 | 51 | 21 |

The sentences column counts obligation-bearing sentences that produced a numbered item. Items meet or exceed sentences in every row, and exceed them in nine of ten, because one sentence in this instruction routinely carries two asks: a rule with its negative case bolted onto the same line, or a table row that pins a field name alongside its legal values. The fourth column counts obligations held out under Declared but ungraded below, none of which any shipped grader can observe. Adding the third column to the fourth gives every obligation the instruction states.

## Declared but ungraded

Every line below is an ask the instruction really makes. None of them reaches a shipped grader, and the reason is recorded rather than left implied, because an obligation dropped in silence is indistinguishable from one nobody noticed.

- `C-CN` `constraint` The product models no purchase order. `src: Constraints bullet 1` why: absence of an endpoint the brief never named is not enumerable
- `C-CN` `constraint` The product models no goods receipt. `src: Constraints bullet 1` why: absence of an endpoint the brief never named is not enumerable
- `C-CN` `constraint` The product models no shipment. `src: Constraints bullet 1` why: absence of an endpoint the brief never named is not enumerable
- `C-CN` `constraint` The product models no picking step. `src: Constraints bullet 1` why: absence of an endpoint the brief never named is not enumerable
- `C-CN` `constraint` The product models no despatch step. `src: Constraints bullet 1` why: absence of an endpoint the brief never named is not enumerable
- `C-CN` `constraint` The product models one warehouse only. `src: Constraints bullet 2` why: absence of a second tenant is not enumerable
- `C-CN` `constraint` The product models no bin. `src: Constraints bullet 2` why: absence of a table the brief never pinned is not enumerable
- `C-CN` `constraint` The product models no location. `src: Constraints bullet 2` why: absence of a table the brief never pinned is not enumerable
- `C-CN` `constraint` The product models no lot. `src: Constraints bullet 2` why: absence of a table the brief never pinned is not enumerable
- `C-CN` `constraint` The product models no serial number. `src: Constraints bullet 2` why: absence of a column the brief never pinned is not enumerable
- `C-CN` `constraint` A reservation never expires. `src: Constraints bullet 3` why: an expiry that never fires leaves no observable trace inside a graded run
- `C-CN` `constraint` A reservation is never edited. `src: Constraints bullet 3` why: absence of an endpoint the brief never named is not enumerable
- `C-CN` `constraint` A reservation is never partially released. `src: Constraints bullet 3` why: absence of an endpoint the brief never named is not enumerable
- `C-CN` `constraint` A reservation never transfers between planners. `src: Constraints bullet 3` why: absence of an endpoint the brief never named is not enumerable
- `C-CN` `constraint` The product offers no password reset. `src: Constraints bullet 4` why: absence of an endpoint the brief never named is not enumerable
- `C-CN` `constraint` The product offers no single sign-on. `src: Constraints bullet 4` why: absence of an endpoint the brief never named is not enumerable
- `C-CN` `constraint` The product offers no second factor. `src: Constraints bullet 4` why: login succeeding in one call already covers the absence of a second step
- `C-CN` `constraint` The product offers no backdated adjustment. `src: Constraints bullet 5` why: absence of a field the brief never pinned is not enumerable
- `C-CN` `constraint` The product offers no approval step on an adjustment. `src: Constraints bullet 5` why: absence of a workflow the brief never pinned is not enumerable
- `C-CN` `constraint` The product sends no email. `src: Constraints bullet 6` why: no email slot is declared, so no inbox exists for a grader to read
- `C-CN` `constraint` The product accepts no file upload. `src: Constraints bullet 6` why: absence of an endpoint the brief never named is not enumerable
- `C-CN` `constraint` The product offers no export. `src: Constraints bullet 6` why: absence of an endpoint the brief never named is not enumerable
- `C-CN` `constraint` The product carries no cost anywhere. `src: Constraints bullet 7` why: absence of a field the brief never pinned is not enumerable
- `C-CN` `constraint` The product carries no price anywhere. `src: Constraints bullet 7` why: absence of a field the brief never pinned is not enumerable
- `C-CN` `constraint` The product carries no currency anywhere. `src: Constraints bullet 7` why: absence of a field the brief never pinned is not enumerable
- `C-CN` `constraint` The product integrates no third party beyond the one named service. `src: Constraints bullet 8` why: no egress exists at run time, so nothing distinguishes a second integration from a dead one
- `C-CN` `constraint` The product makes no external network call at run time. `src: Constraints bullet 9` why: the environment blocks egress, so the constraint is enforced by the harness
- `C-TR` `contract` The frontend uses React 18 with Vite. `src: Technical requirements bullet 1` why: no black-box observation distinguishes one frontend framework from another
- `C-TR` `contract` The frontend uses TypeScript in strict mode. `src: Technical requirements bullet 1` why: a compile-time setting leaves no runtime trace
- `C-TR` `contract` The frontend uses Tailwind CSS v3. `src: Technical requirements bullet 1` why: computed styles cannot be attributed to one CSS toolchain
- `C-TR` `contract` The frontend uses TanStack Query for server state. `src: Technical requirements bullet 1` why: a client cache library leaves no observable HTTP signature
- `C-TR` `contract` The frontend uses React Router v6. `src: Technical requirements bullet 1` why: routing behaviour is graded, the router that produces the behaviour is not observable
- `C-TR` `contract` The frontend uses react-hook-form for the reserve form. `src: Technical requirements bullet 1` why: form behaviour is graded, the form library is not observable
- `C-TR` `contract` The frontend uses react-hook-form for the adjust form. `src: Technical requirements bullet 1` why: form behaviour is graded, the form library is not observable
- `C-TR` `contract` A typed fetch wrapper injects the bearer token. `src: Technical requirements bullet 1` why: the header is graded, the code path that sets the header is internal
- `C-TR` `contract` The backend uses Python 3.12 with FastAPI on Uvicorn. `src: Technical requirements bullet 2` why: INV6 forbids inspecting the agent source, so no response header is pinned
- `C-TR` `contract` The backend speaks REST over JSON. `src: Technical requirements bullet 2` why: the pinned route table already covers every observable half of the claim
- `C-TR` `contract` The backend uses Pydantic v2. `src: Technical requirements bullet 2` why: a validation library leaves no pinned observable trace
- `C-TR` `contract` The backend uses SQLAlchemy 2.0 with typed models. `src: Technical requirements bullet 3` why: the rows are graded, the ORM that wrote them is not observable
- `C-TR` `contract` The backend uses Alembic for forward-only migrations. `src: Technical requirements bullet 3` why: the schema is graded, the migration tool is not observable
- `C-TR` `contract` Auth is in-app JWT HS256. `src: Technical requirements bullet 4` why: the token works or the token does not, so the signing algorithm stays internal
- `C-TR` `literal` The JWT expiry is eight hours. `src: Technical requirements bullet 4` why: an eight-hour boundary cannot be reached inside a graded run without wall-clock dependence
- `C-TR` `contract` Passwords are hashed with bcrypt through passlib. `src: Technical requirements bullet 4` why: the hash algorithm is not exposed on any surface the brief pins
- `C-TR` `constraint` The application introduces no second database. `src: Technical requirements para 2` why: absence of an unnamed component cannot be observed from outside
- `C-TR` `constraint` The application introduces no cache. `src: Technical requirements para 2` why: absence of an unnamed component cannot be observed from outside
- `C-TR` `constraint` The application introduces no queue. `src: Technical requirements para 2` why: absence of an unnamed component cannot be observed from outside
- `C-TR` `constraint` The application introduces no object store. `src: Technical requirements para 2` why: absence of an unnamed component cannot be observed from outside
- `C-TR` `constraint` The application introduces no realtime broker. `src: Technical requirements para 2` why: absence of an unnamed component cannot be observed from outside
- `C-TR` `constraint` The application introduces no vendor SDK. `src: Technical requirements para 2` why: a correct hand-written client is indistinguishable from a vendor SDK over the wire
- `C-TR` `constraint` The application downloads no copy of PostgreSQL. `src: Technical requirements postgresql` why: build-time behaviour lies outside every grading window
- `C-TR` `constraint` The application starts no copy of PostgreSQL. `src: Technical requirements postgresql` why: a second copy on the internal network is not enumerable from the app surface
- `C-TR` `constraint` Structured single-line logs reach stdout. `src: Technical requirements bullet 2` why: the graders reach the app over HTTP with no view of its log stream
- `C-TR` `constraint` No password reaches the log stream. `src: Technical requirements bullet 2` why: the graders reach the app over HTTP with no view of its log stream
- `C-DM` `constraint` The seeded password is hashed like any other password. `src: Data model para 2` why: no endpoint returns a password hash, so absence of clear text is unobservable
- `C-DM` `data` Every timestamp is UTC. `src: Data model para 1` why: no assertion may compare a stored timestamp against a clock read inside a graded run
- `C-DM` `constraint` No fractional quantity exists anywhere. `src: Data model para 1` why: absence of a type the brief never pinned is not enumerable over JSON
- `C-DM` `constraint` No money exists anywhere. `src: Data model para 1` why: absence of a field the brief never pinned is not enumerable
- `C-DC` `contract` A `.browser_screenshots/` directory exists at the app root. `src: Deployment contract bullet 6` why: the graders reach the app over HTTP with no view of its filesystem
- `C-DC` `contract` A `.downloads/` directory exists at the app root. `src: Deployment contract bullet 6` why: the graders reach the app over HTTP with no view of its filesystem
- `C-DC` `contract` Both reserved directories are left empty. `src: Deployment contract bullet 6` why: the graders reach the app over HTTP with no view of its filesystem
- `C-DC` `contract` The frontend is a production build behind a preview server. `src: Deployment contract bullet 7` why: a production build is indistinguishable from a dev server over the pinned HTTP surface
- `C-DC` `constraint` The frontend is never served by a dev server. `src: Deployment contract bullet 7` why: a production build is indistinguishable from a dev server over the pinned HTTP surface
- `C-DC` `contract` The server is started fully detached. `src: Deployment contract bullet 8` why: the start mechanism is invisible, so its outcome is covered by the server outliving the session
- `C-DC` `contract` The listening process has a parent that is not the agent shell. `src: Deployment contract bullet 10` why: process ancestry is not reachable from any grader; the harness observes it at G18
- `C-DC` `contract` The published port still answers after the session ends. `src: Deployment contract bullet 10` why: the harness owns the session boundary, so G18 rather than a grader observes the moment
- `C-DC` `constraint` The app downloads no copy of a backing service. `src: Deployment contract bullet 11` why: build-time behaviour lies outside every grading window
- `C-DC` `constraint` The app installs no copy of a backing service. `src: Deployment contract bullet 11` why: build-time behaviour lies outside every grading window
- `C-DC` `constraint` The app compiles no copy of a backing service. `src: Deployment contract bullet 11` why: build-time behaviour lies outside every grading window
- `C-DC` `constraint` The app starts no copy of a backing service. `src: Deployment contract bullet 11` why: a second copy on the internal network is not enumerable from the app surface
- `C-DC` `constraint` The app uses no provider beyond the one named. `src: Deployment contract bullet 12` why: absence of a second provider on the internal network is not enumerable
- `C-DC` `constraint` The app uses no edge function. `src: Deployment contract bullet 12` why: no edge runtime exists in the environment, so the constraint is enforced rather than observed
- `C-DC` `constraint` The app uses no persistent volume. `src: Deployment contract bullet 13` why: container topology is a harness property, decided at G15, never by a grader
- `C-DC` `constraint` The app uses no fixed container name. `src: Deployment contract bullet 13` why: container topology is a harness property, decided at G15, never by a grader
- `C-DC` `constraint` The app uses no custom network. `src: Deployment contract bullet 13` why: container topology is a harness property, decided at G15, never by a grader
- `C-DC` `constraint` The refusal path never leans on an application pre-check alone. `src: Deployment contract no shortcuts` why: covered behaviourally by the contention observation, since a pre-check is not itself visible
- `C-DC` `constraint` No ledger line is edited after the fact. `src: Deployment contract no shortcuts` why: absence of an endpoint the brief never named is not enumerable
- `C-DC` `constraint` No ledger line is deleted after the fact. `src: Deployment contract no shortcuts` why: absence of an endpoint the brief never named is not enumerable

Ungraded obligations: 77.
