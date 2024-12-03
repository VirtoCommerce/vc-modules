# Virto Commerce Modules

At Virto Commerce, we provide frequent releases for various modules, packed with new features, enhancements and fixes.

Generally, we have three release channels:
- Stable.
- Edge.
- Preview.

Depending on your needs and development cycle, you can choose a release strategy that suits you best.

This repository contains registers of Virto Commerce modules categorized into Alfa, Edge, and Stable Bundles.

## Alfa Bundle
The [Alfa Bundle](modules_v3.json) includes the latest features and updates that are still in the experimental phase. These modules are intended for testing and feedback purposes.

## Edge Bundle
The [Edge Bundle](modules_v3.json) contains modules that have been tested and are more stable than the Alfa Bundle but may still undergo changes. These modules are suitable for early adopters who want to take advantage of new features before they are fully stabilized.

## Stable Bundles
The [Stable Bundles folder](/bundles) include modules that have been thoroughly tested and are considered production-ready. These modules are recommended for use in live environments.

For more detailed information on the release strategy and the different bundles, please refer to the [Virto Commerce Release Strategy Overview](https://docs.virtocommerce.org/platform/developer-guide/Updating-Virto-Commerce-Based-Project/release-strategy-overview/).

## Private Modules
Virto Commerce also provides private modules that are not included in the public repository. These modules are available to customers with specific requirements, such as AI, Enterprise, High performance, and Marketplace capabilities. If you need access to private modules, please [contact us](https://virtocommerce.com/request-demo).

## Packaged Business Capabilities
Packaged Business Capabilities (PBCs) are a core component of Virto Commerce's modular and flexible approach, known as the Virto Atomic Architecture. These PBCs are designed to encapsulate specific business functionalities, making them an ideal choice for decision-makers across various business entities.

Virto Commerce currently offers PBCs:

* **Virto Start**: Ideal for businesses that want a quick and hassle-free start with common B2B and B2C e-commerce configurations. This package is perfect for getting up and running swiftly, with native integration with Virto Commerce Frontend.
* **Identity Provider (IdP)**: Virto Commerce can be used as an Identity Provider, essential for organizations needing secure and efficient user identity management. This system authenticates users' identities and authorizes their access to various applications and services, enhancing security and streamlining customer authentication processes.
* **Digital Catalog**: A must-have if you need to grant access to your catalog data via Frontend or API without the ability to buy products. This package supports modern scenarios with advanced search, browsing, and filtering capabilities, making it ideal for businesses that require robust catalog management solutions.
* **Purchase**: This package is crucial if you already have an e-commerce catalog or are building a marketplace that aggregates catalog data from multiple vendor APIs, like Amazon, Booking, etc. Virto Commerce can be used to build cart and checkout experiences for placing orders.
* **Product Information Management (PIM)**: If you need just a PIM, Virto Commerce can play this role by granting access for category managers, building, and improving e-commerce catalogs. PIM is indispensable for companies looking to streamline their product data management to match specific business needs.
* **Customer & Organizations (CRM)**: If you need just a CRM, Virto Commerce can play this role, allowing you to grant access to CRM data. This package is essential for managing customer interactions and data throughout the customer lifecycle, improving business relationships and customer retention.
* **🔥 You idea here**: We can help you to create a custom PBC for your business needs.

You can find packages by [following link](/pbc). 

and install using the following command:

```cmd
vc-build install -PackageManifestPath "TODO:Path to papackage.json"
```

For more information on PBCs, please refer to the [Virto Commerce Packaged Business Capabilities Overview](https://docs.virtocommerce.org/platform/developer-guide/Getting-Started/Installation-Guide/pbcs/)
