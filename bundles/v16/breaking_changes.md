# Stable 16: Breaking changes

This is the reference for code that moves from **Stable 15** (platform `3.1039.x`) to **Stable 16** (platform `3.1076.0`, theme
`2.58.0`, 59 modules). It covers:
1. The platform's move from Hangfire to the engine-agnostic **job API**, and what that means for every module.
2. The obsolete members removed in **VCST-5901** (expired `VC0009`–`VC0012`).
3. The new obsolete warning (**VC0015**) on synchronous indexing methods.
4. Per-module signature and behavior changes from the Stable 16 release PRs (**VCST-6042**).

The procedure lives in [update_path.md](update_path.md), and the per-version module notes are in [release_notes.md](release_notes.md).

---

## 1. Background jobs: `VirtoCommerce.Platform.Hangfire` is retired

The platform no longer depends on Hangfire. Job contracts are in **`VirtoCommerce.Platform.Core`**
(`VirtoCommerce.Platform.Core.Jobs`). The engine (Hangfire by default, or RabbitMQ / InMemory) is the
**`VirtoCommerce.BackgroundJobs`** module (3.1052.0 in this bundle).

| What | Stable 15 | Stable 16 |
|---|---|---|
| `VirtoCommerce.Platform.Hangfire` NuGet | `3.1039.x` | **frozen at `3.1051.0`, no `3.1076.0`**. Remove the reference: vc-build's `MatchVersions` requires every `VirtoCommerce.Platform.*` ref to equal the platform version. |
| Running jobs | built into the platform | **requires the `VirtoCommerce.BackgroundJobs` module** (it's in the bundle; install it with any custom set of modules) |
| One-off job | `BackgroundJob.Enqueue(() => x.Method(args))` | payload class + `IBackgroundJobHandler<TPayload>`, registered with `services.AddBackgroundJob<THandler, TPayload>()`, enqueued with `IBackgroundJob.Enqueue<THandler>(payload)` (or the static `VirtoCommerce.Platform.Core.Jobs.BackgroundJob.Enqueue<THandler>(payload)` facade) |
| Recurring job | `IRecurringJobService.WatchJobSetting(new SettingCronJobBuilder()...)` in `PostInitialize` | `services.AddRecurringJob<THandler, TPayload>(s => s.WithId("<legacy id>").FromSettings(enabledSetting, cronSetting))` in `Initialize` |
| Cancellation / context | `IJobCancellationToken`, `PerformContext` | `CancellationToken` + `IJobExecutionContext` (`JobId`); cancel with `IBackgroundJob.Cancel(jobId)` |
| `[DisableConcurrentExecution(N)]` | Hangfire attribute | `IDistributedLock.TryExecuteAsync(resource, ..., TimeSpan.FromSeconds(N))` (skip and log), or `ExecuteAsync` (wait, then throw so the engine retries) |
| Delayed job (`Schedule(..., delay)`) | Hangfire | **no equivalent**: the job API is fire-and-forget (webhooks' 5 s delay was dropped) |

**Compatibility.** BackgroundJobs ships a type-forwarding `VirtoCommerce.Platform.Hangfire.dll`, and
`BackgroundJobs:EnableLegacyHangfire` defaults to `true`. So a custom module that still calls the Hangfire API directly
keeps working **at runtime** once BackgroundJobs is installed. It has to migrate only when it is rebuilt against platform
3.1076.0.

**Jobs queued before the upgrade.** Legacy Hangfire jobs in durable storage (`JobStorageType = Database`) still run after
the upgrade if their target method exists with the same signature. Where a module renamed or removed a target that
users would miss, it keeps a byte-identical stub marked `[Obsolete(DiagnosticId = "VC0015")]` that re-enqueues onto the new handler
(listed per module below). Recurring jobs keep their old Hangfire id (`{Type}.{Method}`), so the new schedule replaces the
old entry instead of leaving it to fail.

---

## 2. New obsolete warning: VC0015

`TreatWarningsAsErrors=true` turns these into build errors. Fix them as the attribute recommends:

| Obsolete member (VC0015) | Module | Replacement |
|---|---|---|
| `IIndexingJobService.EnqueueIndexAndDeleteDocuments(IList<IndexEntry>, string, IList<IIndexDocumentBuilder>)` | Search 3.1010.0 | `await EnqueueIndexAndDeleteDocumentsAsync(indexEntries, priority, builders, cancellationToken)`, or return its task from a method that already returns `Task` |
| `IIndexingJobService.Enqueue(string user, IndexingOptions[])` | Search 3.1010.0 | `await EnqueueAsync(user, options, cancellationToken)` |
| Legacy Hangfire entry points kept as stubs (section 4) | several | not called by new code; they only serve already-queued legacy jobs |

In Moq setups and verifies, the async methods need `It.IsAny<CancellationToken>()` for the optional last parameter, which expression trees can't omit, and `.ReturnsAsync`.

---

## 3. Removed expired obsolete members (VCST-5901)

Members that were already `[Obsolete]` (no `DiagnosticId`, or `VC0009`–`VC0012`) are removed. None of them are used in the
bundle; the risk is in external code.

| Module (version) | Removed | Replacement |
|---|---|---|
| Assets 3.1010.0 | `AssetsModule.Core.Swagger.UploadFileAttribute` | `VirtoCommerce.Platform.Core.Swagger.UploadFileAttribute` (same properties) |
| Core 3.1012.0 | `CoreModule.Core.Seo.ISeoBySlugResolver`, `SeoInfo`, `SeoSearchCriteria` (the whole `VirtoCommerce.CoreModule.Core.Seo` namespace) | `VirtoCommerce.Seo.Core.Services.ISeoResolver`, `VirtoCommerce.Seo.Core.Models.SeoInfo` / `SeoSearchCriteria`; drop stale `using VirtoCommerce.CoreModule.Core.Seo;` |
| Catalog 3.1048.0 | `ProductDocumentBuilder.CreateDocument(...)` (2 overloads), `IndexLocalizedName(document, localizedString)` (protected virtual) | override `CreateDocumentAsync(...)`; use the `(document, localizedString, catalogLanguages, fallbackValue)` overload |
| Customer 3.1028.0 | `Contact.SelectedAddressId` (+ `ContactEntity` column, dropped by the `DropSelectedAddressId` migration); obsolete `MemberResolver(IMemberService, Func<UserManager<ApplicationUser>>, IPlatformMemoryCache)` ctor | `ICustomerPreferenceService.GetSelectedAddressId` / `SaveSelectedAddressId`; the `IRequestScopedCacheAccessor` constructor |
| Inventory 3.1010.0 | REST `POST api/inventory/inventories/search`, `POST api/inventory/inventory/product/inventories/search`; `IInventoryService.GetByIdsAsync`, `GetProductsInventoryInfosAsync`; `SearchInventoriesAsync`, `SearchProductInventoriesAsync`; `SearchAllProductInventoriesNoCloneAsync`; `BuildQuery(IInventoryRepository, ...)` | the `inventory/search` / `inventory/product/search` routes; `GetAsync`; `IInventorySearchService.SearchAsync`; `SearchAsync`; `SearchAllNoCloneAsync`; `BuildQuery(IRepository, ...)` |
| Marketing 3.1009.0 | `IContentItemsSearchService`, `IContentPlacesSearchService`, `IContentPublicationsSearchService`, `IFolderSearchService`, `IDynamicContentService` (+ impls) and 7 cache regions; obsolete methods on the promotion/coupon/usage service and search interfaces; `AmountBasedReward.GetRewardAmount(decimal, int)`; two `BestRewardPromotionPolicy.GetBestAmountReward` overloads; `PromotionEvaluationContext.OrganizaitonId` | the non-obsolete members the `[Obsolete]` messages pointed to (see vc-module-marketing#279); `OrganizationId` |
| Orders 3.1018.0 | `OperationExtensions.FillAllChildOperations`; `CancelPaymentOrderChangedEventHandler.CancelPayment(PaymentIn, CustomerOrder)` (protected virtual); `ISupportPartialPriceUpdate` | `Core.Extensions.OperationExtensions.FillChildOperations()`; override `CancelPaymentAsync(...)`; none |
| Payment 3.1010.0 | sync `ProcessPayment`, `PostProcessPayment`, `VoidProcessPayment`, `CaptureProcessPayment`, `RefundProcessPayment`, `ValidatePostProcessRequest` on payment methods | override the `*Async` counterparts. **Runtime:** a provider that overrode only the sync method now hits `NotImplementedException` until it overrides `*Async`. |
| ProfileExperienceApi 3.1020.0 | GraphQL query **`requestPasswordReset`**; `RequestPasswordResetQuery` / `Handler` | `sendPasswordResetEmail` (clients sending the old query fail at runtime) |
| Xapi 3.1026.0 | `IUserManagerCore.CheckUserState(string, bool)`; `Xapi.Core.Extensions.SeoInfosExtensions`; `GetStoreQueryHandler.ResolveStoreByDomain`; `QueryArgumentPresets.GetArgumentForDynamicProperties` | `CheckCurrentUserState(IResolveFieldContext, bool)`; the `Seo.Core` / Store SEO extensions |
| XCart 3.1038.0 | `CartAggregate` constructor's **`ICartSharingService`** parameter; `CartAggregate.ValidateAsync(CartValidationContext, string)`, `ValidationErrors`, `Scope`; `ModuleConstants.ListTypeName` / `PrivateScope` / `OrganizationScope`; `CartAggregateResponseGroup` | drop the argument (DI / `AbstractTypeFactory` construction is unaffected) and pass an `IXCartMapper` (AutoMapper was removed in VCST-5661); override `ValidateAsync(string)` |
| XCatalog 3.1023.0 | `OutlineExtensions.GetSeoPath`, `GetOutlinePath`, `GetBreadcrumbsFromOutLine`, `SeoInfoForStoreAndLanguage`; `IndexSearchRequestBuilder.AddTerms(...)` (2 overloads) | `CatalogModule.Core.Extensions.OutlineExtensions.*`; `GetBreadcrumbs(store, cultureName)`; `StoreModule.Core.Extensions.GetBestMatchingSeoInfo()`; `AddTermFilter()` |

---

## 4. Per-module changes from the Stable 16 release (VCST-6042)

Only modules with a change beyond the version bumps are listed. "Legacy stub" means a VC0015 `[Obsolete]` member kept only so that
already-queued Hangfire jobs still find their target.

| Module (version) | Compile-time changes | Runtime / behavior | Legacy stubs (VC0015) |
|---|---|---|---|
| AvalaraTax 3.1005.0 | `OrdersSynchronizationJob.RunScheduled(IJobCancellationToken, PerformContext)` → `RunScheduled(CancellationToken)`; `RunManually(..., IJobCancellationToken, PerformContext)` → `RunManually(..., string jobId, CancellationToken)`; `AvaTaxController.CancelOrdersSynchronization` is `async` | enabling or disabling the schedule, or changing its cron, takes effect without a restart | — |
| BulkActionsModule 3.1004.0 | removed `IBackgroundJobExecutor` / `BackgroundJobExecutor` (use `IBackgroundJob`); `BulkActionsController` takes `IBackgroundJob`; `BulkActionJob` is an `IBackgroundJobHandler<BulkActionJobPayload>`; `Cancel` is `async` | HTTP contract unchanged | none: the old signature needed Hangfire types |
| Cart 3.1011.0 | — | recurring jobs: an occurrence that can't get the lock in 10 s is **skipped and logged** (it used to fail and retry) | — |
| CatalogCsvImportModule 3.1007.0 | `ExportImportController` constructor drops `ICurrencyService`, `IBlobUrlResolver`, `ICsvCatalogExporter`, `ICsvCatalogImporter`, `IExportFileNameBuilder`, `ILogger<>` | HTTP contract unchanged | `BackgroundImport`, `BackgroundExport` |
| CatalogPersonalization 3.1006.0 | `TaggedItemOutlinesSynchronizationJob.Run(notification, IJobCancellationToken, PerformContext)` removed (protected `Run(..., string jobId, CancellationToken)`); `PerformSynchronization` takes `CancellationToken`; the job's ctor gains `ISettingsManager`; `PersonalizationModuleController` ctor gains `IBackgroundJob`; `CancelSynchronization` is `async` | **new setting `CatalogPersonalization.EnableOutlinesSynchronizationJob`** (bool, default `true`) enables the schedule; the job does nothing unless `TagsInheritancePolicy` is UpTree | `LogEntityChangesInBackgroundAsync` |
| CatalogPublishing 3.1007.0 | `CompletenessController` ctor gains `IBackgroundJob`, drops `IProductIndexedSearchService` | — | `EvaluateCompletenessJob` |
| Content 3.1006.0 | `LogChangesChangedEventHandler.InnerHandle<T>` (protected virtual) returns `Task`: **an override with the old `void` signature is silently skipped**, so recompile it | — | `LogEntityChangesInBackground` |
| Contracts 3.1006.0 | `DeleteContractHandler` has a parameterless ctor; `Handle` is `async` | — | `DeletePricelistAssignmentsAsync`, `DeleteAllContractsMembersAsync` |
| CustomerReviews 3.1007.0 | — | `RequestCustomerReviewJob.Process` loses `[DisableConcurrentExecution]`; the lock is in `RequestCustomerReviewJobHandler` (skip and log) | none needed: `TryToSendOrderNotificationsAsync` keeps its signature |
| DynamicAssociationsModule 3.1003.0 | — | — | `LogEntityChangesInBackground` |
| Export 3.1005.0 | `ExportJob` is an `IBackgroundJobHandler<ExportJobPayload>`; `ExportController.CancelExport` is `async` | HTTP contract unchanged | none: the old signature needed Hangfire types |
| Marketing 3.1009.0 | `LogChangesChangedEventHandler.InnerHandle<T>` returns `Task` (same caveat as Content); `MarketingModulePromotionController` ctor drops `IBlobStorageProvider`, `CsvCouponImporter` | — | `LogEntityChangesInBackground`, `BackgroundImportAsync` |
| Notifications 3.1018.0 | internal move to `IBackgroundJob` | — | `RequestPasswordResetHandler.TryToSendNotificationsAsync` (restored) |
| PageBuilderModule 3.1031.0 | `PageBuilderSharedComponentContentChangedEventHandler` ctor drops `IBackgroundJobClient`, `Handle` is `async`; `PageBuilderSharedComponentContentPropagationJob.ProcessAsync` takes `CancellationToken`; `PagesMigrationService` and `PageBuilderAssetReferenceMigrationService` ctors gain `IBackgroundJob` | — | — |
| PushMessages 3.1007.0 | `PushMessageJobService` recurring methods take `CancellationToken`; **`UsePushMessageJobs(IApplicationBuilder)` removed**, call `services.AddPushMessageJobs()` in `Initialize` | — | — |
| Return 3.1004.0 | `ReturnStatusNotificationHandlerBase.EnqueueSending(ReturnNotificationJobArgument)` (protected abstract) returns `Task` | — | none needed: `SendNotificationsAsync` / `SendPushMessagesAsync` keep their signatures |
| Seo 3.1005.0 | internal move to `IBackgroundJob` | — | none (loss negligible) |
| Subscription 3.1005.0 | — | recurring jobs: skipped and logged on lock contention (it used to fail and retry) | — |
| UCP 3.1010.0 | — | **now declares `VirtoCommerce.XOrder` ≥ 3.1014.0** in `module.manifest` (it already needed it at runtime) | — |
| WebHooks 3.1005.0 | internal move to `IBackgroundJob` | **the 5-second delivery delay is gone**: webhooks are sent immediately | none needed: `WebHookManager.NotifyAsync` keeps its signature |

Each module's `module.manifest` dependency floors are raised to the Stable 16 versions. Third-party package versions are
aligned to the platform's ([platform_package_reference.md](platform_package_reference.md)).

---

## 5. Platform 3.1076.0: local development

Beyond section 1, the Stable 16 platform PR (vc-platform#3126) changes no signatures; for the full 3.1039 → 3.1076 platform changelog see the
[vc-platform releases](https://github.com/VirtoCommerce/vc-platform/releases) ([release_notes.md](release_notes.md) covers the modules). Local-development changes from that PR:
- The Web project's user-secrets id is now `VirtoCommerce.Platform.Web` (was `local`). Move
  `%APPDATA%\Microsoft\UserSecrets\local\secrets.json` to `...\VirtoCommerce.Platform.Web\secrets.json`.
- In `Development`, `Assets:FileSystem:PublicUrl` / `Content:FileSystem:PublicUrl` default to `http://localhost:10645/...`.
- `DockerCompose/ModulesDevelop`:
  - the container listens on port 8080, and the host port stays 8090;
  - the default search provider is `ElasticSearch8`;
  - `DB_PASS`, `REDIS_PASS`, `MODULES_VOLUME` and `APP_DATA_MODULES` are now required.
- The root `docker-compose` and the `Docker` launch profile are removed; use `DockerCompose/ModulesDevelop` or the published image.
