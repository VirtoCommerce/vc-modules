# Stable 15 — Breaking changes

This document records obsolete code removed during the Stable 15 release cycle and how to
adapt downstream code. Removal policy: members marked `[Obsolete]` with **no DiagnosticId** or
**DiagnosticId VC0001–VC0011** (strictly `< VC0012`) are removed; **VC0012+** are kept.

See [obsolete_removal_audit.md](obsolete_removal_audit.md) for the full pre-release inventory and
[dependency-tree.md](dependency-tree.md) for the wave order.

---

## Wave 0 — Platform (`vc-platform` → 3.1039.0)

5 dead/obsolete members removed. **None had any usage inside `vc-platform`** (src or tests), so
the platform build is unaffected. Downstream impact is summarized per item.

| Removed symbol | Kind | DiagId | Replacement | Downstream call sites (in-bundle modules) |
|---|---|---|---|---|
| `StringExtensions.EqualsInvariant(this string, string)` | extension method | VC0010 | `EqualsIgnoreCase()` (identical `OrdinalIgnoreCase` semantics) | **161 call sites / 65 files / 12 repos** — fixed per module wave |
| `IHasLanguage` (interface, `Domain/IHasLanguage.cs` — file deleted) | interface | VC0011 | `VirtoCommerce.Platform.Core.Common.IHasLanguageCode` | core, experience-api (~11 refs) |
| `ConsoleLog` (static class, `Logger/ConsoleLog.cs` — file deleted) | class | VC0010 | Serilog static `Log.Logger` or injected `ILogger` | none in-bundle (only out-of-scope ai-prompts) |
| `PlatformDbContext._idLength64` | protected const | VC0010 | `DbContextBase.Length64` / `UserNameLength` | none |
| `PlatformDbContext._idLength2048` | protected const | VC0010 | `DbContextBase.Length2048` | none |

### How to fix downstream

- **`EqualsInvariant` → `EqualsIgnoreCase`** — mechanical rename; signatures and semantics are
  identical (`string.Equals(a, b, StringComparison.OrdinalIgnoreCase)`). Each consuming module is
  updated when its wave runs (it then compiles against platform 3.1039.0 from `local-nuget`).
- **`IHasLanguage` → `IHasLanguageCode`** — same `LanguageCode` member; change the interface
  reference. Verify implementers expose `LanguageCode { get; }`.
- **`ConsoleLog`** — replace `ConsoleLog.BeginOperation/EndOperation` with `ILogger` logging.
- **`_idLength64` / `_idLength2048`** — derived `DbContext`s should use the public
  `DbContextBase.Length64` / `Length2048` / `UserNameLength` constants.

> Wave 0 status: removals applied on branch `feat/VCST-5163-stable-15`. Baseline build green
> (0/0); verify build after removal **green (0 warnings, 0 errors)**. Platform packed to
> `local-nuget` as **3.1039.0**. Pending: `npm audit fix` (platform Web has no lock file).

---

## Wave 1 — Core (`vc-module-core` → 3.1007.0, platform ref → 3.1039.0)

**Decision (user):** perform the full SEO/Outlines module-extraction migration now.

### Removed (mechanical, 0 call sites)
| Symbol | DiagId | Replacement |
|---|---|---|
| `ConditionTree.WithAvailConditions(params IConditionTree[])` | VC0010 | `WithAvailableChildren()` |
| `ConditionTree.WithChildrens(params IConditionTree[])` | VC0010 | `WithChildren()` |

### Removed (SEO/Outlines types relocated to the `Seo` and `Catalog` modules) — 10 files deleted
| Removed Core type | DiagId | Replacement |
|---|---|---|
| `Seo.ISeoSupport` | VC0010 | `VirtoCommerce.Seo.Core.Models.ISeoSupport` |
| `Seo.ISeoResolver` | VC0010 | `VirtoCommerce.Seo.Core.Services.ISeoResolver` |
| `Seo.ISeoDuplicatesDetector` | VC0010 | `VirtoCommerce.Seo.Core.Services.ISeoDuplicatesDetector` |
| `Seo.CompositeSeoResolver` / `CompositeSeoBySlugResolver` | VC0010 | `VirtoCommerce.Seo.Core.Services.ICompositeSeoResolver` |
| `Seo.SeoSearchCriteria` | VC0010 | `VirtoCommerce.Seo.Core.Models.SeoSearchCriteria` |
| `Data/Seo.NullSeoDuplicateDetector` | VC0010 | `VirtoCommerce.Seo.Data.Services.NullSeoDuplicateDetector` |
| `Outlines.IHasOutlines` | VC0010 | `VirtoCommerce.CatalogModule.Core.Outlines.IHasOutline` |
| `Outlines.Outline` / `OutlineItem` | VC0010 | `VirtoCommerce.CatalogModule.Core.Outlines.Outline` / `OutlineItem` |

### RETAINED in Core for S15 (removal deferred to the next stable release) — user decision
| Kept Core type | DiagId | Reason |
|---|---|---|
| `Seo.ISeoBySlugResolver` (interface only) | VC0010 | Other/external VC modules still consume it; keep one more release as a bridge. Its Core implementation (`CompositeSeoBySlugResolver`) **is** removed. |
| `Seo.SeoInfo` | VC0010 | Required as `ISeoBySlugResolver.FindSeoBySlugAsync`'s return type, so the interface's contract stays unchanged for external consumers. Dropped its now-removed `IHasLanguage` base (kept the `LanguageCode` property). |

During S15, **in-bundle** consumers of `ISeoBySlugResolver` (Catalog `CatalogSeoBySlugResolver`,
Store `StoreSeoBySlugResolver` + their Module.cs registrations) are migrated **off** it in their
waves. The interface itself is removed from Core in the **next** stable release.

In-Core fix: removed the 3 superseded DI registrations in `CoreModule.Web/Module.cs` (the `Seo`
module already registers `ICompositeSeoResolver`/`NullSeoDuplicateDetector`) and the two now-unused
`using` directives. **Core builds green (0/0) against platform 3.1039.0** with `ISeoBySlugResolver`
+ `SeoInfo` retained (unused within Core, so no VC0010 self-error).

### Downstream stragglers to migrate in their waves (still import `VirtoCommerce.CoreModule.Core.Seo/Outlines`)
These compile today against old Core; they must switch to the Seo/Catalog types when their wave runs:
- **Store** (Wave 3) — 2 files
- **Catalog** (Wave 4) — 2 files (catalog already depends on the Seo module; mostly uses the new type already)
- **Xapi / x-api** (Wave 5) — 1 file
- **CatalogPublishing** (Wave 5) — 1 file (Seo + Outlines)

> (`vc-module-experience-api` also uses these but is **not** in the v15 bundle — out of scope.)

### Other Wave 1 modules (no obsolete removals)
Assets `3.1005.0`, Search `3.1004.0`, ApplicationInsights `3.1004.0`, AzureAD `3.1002.0`,
GoogleSSO `3.1002.0`, WebHooks `3.1004.0` — platform ref → 3.1039.0 + `npm audit fix` only; all
build green and compressed to artifacts. (Search's 2 audit "hits" were comment false positives —
the audit scanner was corrected to ignore `[Obsolete` inside comments; bundle total dropped 180 → 159.)

---

## Systemic: `ICancellationToken` → `CancellationToken` migration (platform-upgrade side effect)

**Not an obsolete *removal*** — a forced *migration*. The platform marks `ICancellationToken`
`[Obsolete VC0014]` (kept), but with `TreatWarningsAsErrors=true` any module that **uses** it fails
to build once bumped to platform 3.1039.0. The platform's `IExportSupport`/`IImportSupport` now
expose a modern `CancellationToken` overload (the `ICancellationToken` one throws by default), so the
fix is to implement the modern overload.

**Spread:** ~15 bundle modules (mostly each module's `*ExportImport.cs` helper + `Module.cs` export
/import methods). **Seo (Wave 1) migrated as the template:** `SeoExportImport` + `Module.cs` switched
`ICancellationToken` → `System.Threading.CancellationToken`; builds green. The same change applies to
Catalog, Customer, Order, Marketing, Pricing, Inventory, Content, Notification, Shipping, Payment,
Tax, Subscription, Sitemaps in their waves.

**Wave 2 ICT migrations done:** BulkActions, Export, Notifications, ImageTools. The full migration
per module also required: Hangfire job boundaries (`new JobCancellationTokenWrapper(jobToken)` →
`jobToken.ShutdownToken`), removing null-conditional `?.` on the now-struct token, and fixing unit
tests (mocked/`null`/wrapped tokens → real `CancellationToken`/`CancellationToken.None`/cancelled CTS).
Reusable helper: `src/migrate_ict.ps1`.

---

## Wave 2 — obsolete removals
| Module | Removed | DiagId | Replacement / note |
|---|---|---|---|
| AzureBlobAssets `3.1006.0` | `ConvertToBlobInfo(BlobItem, Uri)` + `ConvertToBlobFolder(BlobHierarchyItem, Uri, BlobContainerProperties)` (dead old overloads) | none | use the public/internal-base-uri overloads. **`CdnUrl` kept** (intentional alias, deferred to next release). |
| ElasticSearch8 `3.1006.0` | `UpdateMappingAsync(string, Properties)`, `ConvertToProviderDocument(IndexDocument, IDictionary)`, `CreateIndexAsync(string, string)`, `ConfigureIndexSettings(IndexSettingsDescriptor)` | VC0011 | use the `documentType`-parameter overloads / `IElasticSearchDocumentConverter`. Internal caller of the obsolete `ConfigureIndexSettings` lived inside the obsolete `CreateIndexAsync` (both removed). |

## Scope decision (Wave 5 onward) — cascading obsoletes deferred
Removing obsolete **interface methods / public API** breaks not only their implementations but also
**downstream modules (later waves) and unit tests** — a large, iterative migration. Per user decision,
from Wave 5 on, S15 does **platform/dep/ICancellationToken bumps + npm audit + CLEAN obsolete removals
only** (dead code, consts, controller actions, `ISeoBySlugResolver` stragglers). **Cascading
interface/public-API obsoletes are KEPT (obsolete-marked) and DEFERRED** to a focused follow-up.

## Wave 5
| Module | Version | Obsolete removed | Deferred (kept) |
|---|---|---|---|
| Cart | 3.1006.0 | `WishlistCartType` const | — |
| CatalogPersonalization | 3.1003.0 | 0 (ICT only) | — |
| Pages | 3.1007.0 | 0 (ICT only) | — |
| Pricing | 3.1003.0 | 0 (ICT only) | — |
| Sitemaps | 3.1003.0 | 0 (ICT only) | — |
| Inventory | 3.1003.0 | 0 (ICT + bump) | 12 (interface-method consolidations: `SearchInventoriesAsync`→`SearchAsync`, `GetByIdsAsync`→`GetAsync`, `BuildQuery`, 2 controller actions) — break downstream + tests |
| Xapi | 3.1011.0 | 1 (`IHasLanguageExtensions.FirstBestMatchForLanguage(IEnumerable<IHasLanguage>)` — required: uses the removed platform `IHasLanguage`) | 16 (SeoInfo extensions, `StoreSettings` props, `SlugInfoQuery.Slug`, `IUserManagerCore.CheckUserState`, etc.) |

## Wave 3 — Store (`3.1005.0`)
| Removed | DiagId | Replacement |
|---|---|---|
| `StoreSeoBySlugResolver : ISeoBySlugResolver` (file deleted + DI registration removed) | VC0010 | `VirtoCommerce.Seo.Core.Services.ISeoResolver` — Store's `StoreSeoResolver` (already registered) supersedes it. This is the planned removal of `ISeoBySlugResolver` *usage* in Store (the interface itself stays in Core for S15). |
| `StoreModuleController.GetStores()` REST action | none | `POST api/stores/search` |

## Wave 4 — Catalog (`3.1029.0`) — partial removal (user decision)
**Removed (clean):** `CatalogSeoBySlugResolver`→`CatalogSeoResolver` (existing); `ModuleConstants.OutlineDelimiter`→`OutlineString.NameDelimiter`; `Data.Model.LocalizedStringEntity<T>`→`Platform.Data.Model.LocalizedStringEntity<T>`; raw-command `GetAllChildrenCategoriesIdsAsync`→`GetChildCategoriesAsync`; obsolete `ProductDocumentBuilder` 4-arg ctor; `CategoryService.PreloadCategoryBranchAsync`/`SearchCategoriesHierarchyAsync` (dead); `Category.Path` obsolete setter.
**Deferred to next release (behavior-affecting):** `ItemResponseGroup.Variations`/`WithVariations` (variation-export flag logic), `ProductDocumentBuilder.CreateDocument` sync→async + `IndexLocalizedName` (indexing call-chain). The VC0014 `ICancellationToken` shim overloads in `SearchServiceExtensions`/`AutomaticLinkService` are kept (compile as-is against platform 3.1039.0; not migrated).

(Customer's `SelectedAddressId` is a persisted DB column — deferred to next release; see release_progress.md.)

## Wave 2 — other platform-upgrade fixes (not removals)
- **Export**: `Microsoft.AspNetCore.Mvc.NewtonsoftJson` 10.0.1 → 10.0.9 (NU1605 downgrade vs platform 3.1039.0's Hangfire); suppressed `VC0015` on the kept `PlatformConstants.Security.Permissions.PlatformExport` (moved to BackupRestore) to avoid an Export→BackupRestore dependency.

## Wave 10 — XOrder (`3.1005.0`) — VC0009 obsolete-usage resolved (not suppressed)
`CreateOrderFromCartCommandHandler` no longer calls XCart's obsolete
`CartAggregate.ValidateAsync(CartValidationContext, ruleSet)` (VC0009). It now calls the
non-obsolete `CartAggregate.ValidateAsync(string ruleSet)`, which builds the validation context
internally (via the aggregate's own `ICartValidationContextFactory`).

**Public API change (downstream impact):** the handler's constructor no longer takes an
`ICartValidationContextFactory` parameter (it was only used to build the now-internal context).
Subclasses / direct constructors must drop that argument; DI registration is unaffected.

**Behavioral note (intended):** validation now runs against products re-resolved for the cart's
*current* items at validation time, rather than the products pre-loaded before `UpdateCart`
removes unselected gift items — so validation reflects the cart as it will be ordered.

Handler unit tests (`CreateOrderFromCartCommandHandlerTests`) updated accordingly and pass green
(`Failed: 0, Passed: 2`). The XCart `ValidateAsync(context, ruleSet)` overload remains
obsolete-marked (VC0009) and kept for the deferred follow-up; only XOrder's *usage* of it is removed.

## Modularity — `IModuleCatalog` (VC0014) usage removed; `ModuleBootstrapper.Instance` → `IHasModuleService`
The platform deprecated the read-only module-query path. The replacement is the DI-registered
`IModuleService` (the `ModuleBootstrapper` singleton, registered as `IModuleService`), or — inside
an `IModule` during `Initialize`/`PostInitialize` — the `IHasModuleService` interface, whose
`ModuleService` property the loader injects before `Initialize` runs.

| Module | Wave | Change | Replaces |
|---|---|---|---|
| XFrontend | 12 | `PageContextQueryHandler` injects `IModuleService`, calls `IsInstalled("VirtoCommerce.WhiteLabeling")` | obsolete `IModuleCatalog.Modules.Any(m => m.ModuleName == …)` (VC0014) |
| Catalog | 4 | `Module` implements `IHasModuleService`; uses `ModuleService.IsInstalled(...)` (3 sites: BulkActions ×2, Export) | static `ModuleBootstrapper.Instance.IsInstalled(...)` |
| Pricing | 5 | `Module` implements `IHasModuleService`; uses `ModuleService.IsInstalled(...)` (Export) | static `ModuleBootstrapper.Instance.IsInstalled(...)` |
| Marketing | 7 | `Module` implements `IHasModuleService`; uses `ModuleService.IsInstalled(...)` (2 sites: Orders) | static `ModuleBootstrapper.Instance.IsInstalled(...)` |

**Downstream guidance for module authors:** to query installed modules from your `Module.cs`,
implement `IHasModuleService` (add `public IModuleService ModuleService { get; set; }`) and call
`ModuleService.IsInstalled(moduleId)` — the loader sets the property before `Initialize`. Elsewhere
(controllers, handlers, services) inject `IModuleService` from DI. Both replace the obsolete
`IModuleCatalog` and the static `ModuleBootstrapper.Instance`. The `using VirtoCommerce.Platform.Modules;`
import is dropped from these `Module.cs` files (the new interfaces live in
`VirtoCommerce.Platform.Core.Modularity`). All four modules rebuilt green and re-staged.
