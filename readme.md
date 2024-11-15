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

* **Virto Start**: Intall and go with common B2B and B2C ecommerce configuration. Native integration with Virto Commerce Frontend. 
* **Identity Provider (IdP)**: System that authenticates users' identities and authorizes their access to various applications and services. Allows for quick and easy authorization and authentication of customers.
* **Digital Catalog**: Ready for creating, managing and browsing a comprehensive digital catalog of products or services. Already includes PIM and rich search xApi capabilities with keyword search, semantic search, personalization, etc. 
* **Product Information Management (PIM)**: Encompasses all functionality that is needed to set up your product catalog. With PIM, you can create and extend the product catalog to match your business needs.
* **Purchase**: The online shopping cart and checkout process act as a gateway for customer and order management.
* **Customer & Organizations (CRM)**: The online shopping cart and checkout process act as a gateway for customer and order management.
* **🔥 You idea here**: We can help you to create a custom PBC for your business needs.

You can find packages by [following link](/pbc). 

and install using the following command:

```cmd
vc-build install -PackageManifestPath "TODO:Path to papackage.json"
```

For more information on PBCs, please refer to the [Virto Commerce Packaged Business Capabilities Overview](https://docs.virtocommerce.org/platform/developer-guide/Getting-Started/Installation-Guide/pbcs/)
