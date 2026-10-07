# Update path → Virto Commerce Stable 16

This guide moves an existing Virto Commerce deployment or custom code base from **Stable 15** to **Stable 16**:
**platform `3.1076.0`**, .NET 10, theme `2.59.0`, 59 modules.

It has two audiences. Read the section that applies, or both:

| You are… | Read |
|---|---|
| **An operator** deploying the published modules (no custom C#) | [Path A](#path-a--operators-deployment) |
| **A developer** with custom modules or a solution that references VC packages | [Path B](#path-b--developers-code) |

> Stable 16 is a **breaking** release, for two reasons. The platform's Hangfire integration moved into the new
> **`VirtoCommerce.BackgroundJobs`** module, behind an engine-agnostic job API. And the expired obsolete members
> (`VC0009`–`VC0012`) were removed. **[breaking_changes.md](breaking_changes.md)** has the full inventory and how to fix each
> item, and **[release_notes.md](release_notes.md)** has the per-module notes. This document is the *procedure*; those two
> are the *reference*.

---

## What changed at a glance

- **Platform → `3.1076.0`**. The platform no longer contains Hangfire.
- **New required module: `VirtoCommerce.BackgroundJobs` (3.1052.0).** It is the background-processing engine (Hangfire by default,
  or RabbitMQ / InMemory). **Without it, no background or recurring job runs.** It ships a type-forwarding
  `VirtoCommerce.Platform.Hangfire.dll`, so modules that still use Hangfire directly keep working.
- **59 modules** move to their Stable 16 versions ([package.json](package.json)). All of them use the new job API, and their
  `module.manifest` dependency floors are raised to these versions.
- **Removed expired obsolete members** (VCST-5901). Highlights:
  - `CoreModule.Core.Seo.*` → `Seo.Core.*`
  - XCart `CartAggregate` constructor (no `ICartSharingService`)
  - sync payment-method methods → `*Async`
  - the Inventory REST search routes
  - the GraphQL query `requestPasswordReset` → `sendPasswordResetEmail`
- **New obsolete warning (VC0015)**: the synchronous `IIndexingJobService.EnqueueIndexAndDeleteDocuments` / `Enqueue` → `*Async`.
- **Behavior:**
  - WebHooks are sent immediately (the 5-second delay is gone).
  - When a recurring job finds the previous run still holding its lock, the occurrence is skipped and logged instead of failing and retrying.
  - UCP now requires XOrder.

---

## Path A — Operators (deployment)

There's no code to change, so this is a version roll-forward of the bundle.

1. **Back up** the database and the `modules` folder, or snapshot the container or volume.
2. **Drain the background queue if you can.** Jobs that Hangfire queued before the upgrade still run afterwards: the
   modules keep the old entry points or use the same signatures. Long manual operations, such as an export or a bulk
   action, that were running during the upgrade are not resumed and must be started again.
3. Point your deployment at the Stable 16 bundle:
   `https://raw.githubusercontent.com/VirtoCommerce/vc-modules/master/bundles/v16/package.json`
   (registered in [stable.json](../stable.json) as `"16"`).
4. Update the platform and modules with the CLI:
   ```powershell
   vc-build InstallPlatform -PlatformVersion 3.1076.0
   vc-build InstallModules                 # resolves module versions from the v16 bundle
   ```
   or run `vc-build Update` against a `vc-package.json` that pins the v16 bundle.
   **If you install a custom set of modules, include `VirtoCommerce.BackgroundJobs`.**
5. **Configure the engine** if you need anything other than the defaults. Everything is set under `VirtoCommerce:BackgroundJobs`
   (`Provider` = `Hangfire` | `RabbitMQ` | `InMemory`, `Mode` = `Producer` | `Worker` | `Both`, `EnableLegacyHangfire`).
   - Existing `VirtoCommerce:Hangfire` settings (storage, dashboard, queues) are honored unchanged.
   - See the [BackgroundJobs README](https://github.com/VirtoCommerce/vc-module-background-jobs#configuration).
6. Start the platform and check **Settings → Modules**: every module **Installed**, **no errors**. On the Hangfire engine, the `/hangfire`
   dashboard should list the recurring jobs under their old ids, for example `DeleteObsoleteCartsJob.Process` and `RequestCustomerReviewJob.Process`.
7. **New setting to review:** `CatalogPersonalization.EnableOutlinesSynchronizationJob` (default `true`). On a DownTree
   tag-inheritance policy (the default), set it to `false` to skip the no-op outline-sync runs.
8. **Re-index** the search catalog (Settings → Search Index → Rebuild).
9. Smoke-test the storefront and admin. If anything fails, restore the backup from step 1.

> Frontend: deploy **`vc-theme-b2b-vue` 2.59.0** (the `ThemeB2BVue` URL in the bundle) to match the API surface.
> If a client still sends the GraphQL query `requestPasswordReset`, switch it to `sendPasswordResetEmail`.

---

## Path B — Developers (code)

Order matters: **bump versions → fix breaking changes → build → test**.

### 0. Prepare
```powershell
git checkout -b feat/update-stable-16        # isolate the change
dotnet build                                  # confirm a clean baseline BEFORE touching anything
```

### 1. Bump versions (mechanical: use the script)
Run **[update-to-stable.ps1](update-to-stable.ps1)** from your repo root. Preview first:

```powershell
./update-to-stable.ps1 -Path . -DryRun       # writes nothing
./update-to-stable.ps1 -Path .               # apply
```

`module.manifest` dependency versions come straight from the Stable 16 bundle: the `package.json` next to the script,
or `-BundleUrl`. `VirtoCommerce.*` NuGet package versions resolve from nuget.org; pin any of them with
`-ModuleVersions @{ 'VirtoCommerce.CatalogModule.Core'='3.1048.0' }`.

| Bumps automatically | You still do by hand |
|---|---|
| `VirtoCommerce.Platform.*` PackageReferences → `3.1076.0` | **Remove `VirtoCommerce.Platform.Hangfire`** and migrate (step 2). The script lists every reference to it. |
| Other `VirtoCommerce.*` PackageReferences → their Stable 16 versions | All other code-level breaking changes (step 3) |
| `module.manifest` `<platformVersion>` and `<dependency>` versions | `npm audit fix` in admin-UI web projects (step 4) |
| (opt.) `<module><version>` for module authors (`-BumpManifestVersion -ManifestVersion <new>`) | Re-index / data migrations |

### 2. Migrate background jobs off Hangfire
`VirtoCommerce.Platform.Hangfire` has no 3.1076.0, and vc-build's `MatchVersions` requires every `VirtoCommerce.Platform.*`
reference to equal the platform version, so remove the reference. **Do not** add a `VirtoCommerce.BackgroundJobs`
package or manifest dependency: the contracts are in `VirtoCommerce.Platform.Core` (`VirtoCommerce.Platform.Core.Jobs`).

**One-off job:** `BackgroundJob.Enqueue(() => x.DoWork(args))` becomes a payload + handler:
```csharp
public class DoWorkJobPayload            // serialized into the job store: keep it a plain class
{
    public string[] Ids { get; set; }
}

public class DoWorkJobHandler(IMyService service) : IBackgroundJobHandler<DoWorkJobPayload>
{
    public virtual Task Execute(DoWorkJobPayload payload, IJobExecutionContext context, CancellationToken cancellationToken = default)
        => service.DoWorkAsync(payload.Ids, cancellationToken);
}

// Module.Initialize
serviceCollection.AddBackgroundJob<DoWorkJobHandler, DoWorkJobPayload>(triggerable: false);

// enqueue: inject IBackgroundJob (returns the job id; Cancel(jobId) cancels it) ...
await backgroundJob.Enqueue<DoWorkJobHandler>(payload);
// ... or, where a scoped dependency must not be captured (event handlers resolved once from the root provider):
await VirtoCommerce.Platform.Core.Jobs.BackgroundJob.Enqueue<DoWorkJobHandler>(payload);
```

**Recurring job:** replace `IRecurringJobService.WatchJobSetting(new SettingCronJobBuilder()...)` in `PostInitialize` with a
registration in `Initialize`. Keep the old Hangfire id (`{Type}.{Method}`) so that the Hangfire engine replaces the old entry:
```csharp
serviceCollection.AddRecurringJob<MyJobHandler, MyJobPayload>(schedule => schedule
    .WithId($"{nameof(MyJob)}.{nameof(MyJob.Process)}")
    .FromSettings(MySettings.EnableJob, MySettings.CronJob));   // the enabler is read as a bool
```

| Hangfire | Stable 16 |
|---|---|
| `IJobCancellationToken` / `PerformContext` | `CancellationToken` / `IJobExecutionContext.JobId` |
| `JobAbortedException` | `OperationCanceledException` |
| `[DisableConcurrentExecution(N)]` | `IDistributedLock.TryExecuteAsync(resource, ..., TimeSpan.FromSeconds(N), ct)` (skip and log) or `ExecuteAsync` (wait, then throw so the engine retries) |
| `IBackgroundJobClient.Schedule(..., delay)` | no delayed enqueue: the job API is fire-and-forget |
| tests mocking Hangfire | mock `IBackgroundJob`; for the static facade, call `BackgroundJob.Initialize(serviceProvider)` |

**Jobs already queued in Hangfire.** A legacy job still runs after the upgrade if its target method exists with the same
signature. If you renamed or removed a target whose loss users would notice, keep a byte-identical stub marked
`[Obsolete(..., DiagnosticId = "VC0015")]` that re-enqueues onto the new handler. The bundle modules do this; see
[breaking_changes.md §4](breaking_changes.md#4-per-module-changes-from-the-stable-16-release-vcst-6042).

### 3. Fix the other breaking changes (manual)
Rebuild and let the compiler drive you. Under `TreatWarningsAsErrors=true`, both **removed** members (`CS0246`/`CS0117`/`CS1729`)
and **obsolete usage** (`VC0015`) surface as errors. Common fixes:

| Symptom | Fix |
|---|---|
| `error VC0015` on `EnqueueIndexAndDeleteDocuments` / `IIndexingJobService.Enqueue` | `await …Async(..., cancellationToken)`; in Moq add `It.IsAny<CancellationToken>()` and use `.ReturnsAsync` |
| `VirtoCommerce.CoreModule.Core.Seo` not found | `VirtoCommerce.Seo.Core.Models` / `.Services` (`SeoInfo`, `SeoSearchCriteria`, `ISeoResolver`) |
| `CS1729` on `new CartAggregate(...)` | drop the `ICartSharingService` argument; the mapper parameter is `IXCartMapper` |
| payment method overrides `ProcessPayment` etc. | override `ProcessPaymentAsync` etc.; the sync bridges are gone (otherwise `NotImplementedException` at runtime) |
| `Contact.SelectedAddressId` not found | `ICustomerPreferenceService.GetSelectedAddressId` / `SaveSelectedAddressId` |
| `UsePushMessageJobs(app)` not found | `services.AddPushMessageJobs()` in `Initialize` |
| override of `InnerHandle<T>` (Content, Marketing) or `EnqueueSending` (Return) no longer called / doesn't compile | the method now returns `Task`: change the override and return the enqueue task |
| controller or job constructors changed (CSV export/import, Completeness, PageBuilder, Personalization, …) | only matters if you construct or subclass them; see breaking_changes.md §4 |

The complete list of removed symbols, with the replacement for each, is in **[breaking_changes.md](breaking_changes.md)**.

### 4. Admin-UI dependencies
In each `*.Web` project that has a `package.json` and a lock file:
```powershell
npm audit fix                # never --force
npm run webpack:build
```

### 5. Build & test
```powershell
dotnet build                 # must be 0 errors / 0 warnings (TreatWarningsAsErrors)
dotnet test
```
Then validate end to end against a running stack, with BackgroundJobs installed, using the
**[vc-testing-module](https://github.com/VirtoCommerce/vc-testing-module)** Playwright + pytest suite
(GraphQL / REST / e2e). Run it with `pytest --import-mode=importlib -m "not destructive and not optional"`.

### 6. Ship
Open a PR, and let CI build and test against the freshly bumped dependencies before you merge or promote.
