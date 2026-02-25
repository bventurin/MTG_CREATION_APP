# Section 1: Introduction

The objective of this project is to develop a web application and to demonstrate the principles of scalable cloud architecture through the integration of multiple web services.

The application, called AetherFlow, was designed to allow players of Magic: The Gathering to build, manage, and improve their decks using AI-driven suggestions. The application enables users to import decks and track their collections. It also provides features such as generating QR codes to share their decks, generating analytical plots to check the "mana curve", and attaching promotional vouchers to buy physical cards. The user needs to register to be able to securely create, update, delete, and view their decks in their collection. The application securely stores user data in Supabase (PostgreSQL) and card deck data in Amazon DynamoDB, and is deployed via AWS Elastic Beanstalk.

The CI/CD pipeline used in this project was designed using GitHub Actions to automate the testing, building, and deployment processes.

This report is structured as follows. Section 2 details the project specification and requirements. Section 3 provides the architecture design and services utilized in the project. Section 4 documents the implementation details, Section 5 details the continuous integration, and Section 6 presents the conclusion and personal reflection of the entire project.

# Section 2: Project Specification and Requirements

The AetherFlow application was designed to meet a specific set of functional and non-functional requirements, ensuring a robust, scalable, and feature-rich experience for its users. Table 1 details the core functional capabilities of the system, while Table 2 outlines the non-functional quality attributes required for the cloud architecture.

\begin{table}[htbp]
\caption{Functional Requirements}
\begin{center}
\begin{tabular}{|c|p{0.85\linewidth}|}\hline
 \multicolumn{2}{|c|}{\textbf{Core System Functions requirements}}\\\hline 
\hline
\textbf{ID} & \textbf{Requirement Description} \\
\hline
FR1 & User Authentication: Users must be able to register, log in, and securely manage their session accounts. \\
\hline
FR2 & Deck Management: Users must be able to securely create, view, update, and delete their own custom card decks. \\
\hline
FR3 & Card Search: The system must allow users to search for Magic: The Gathering cards from the synchronized database. \\
\hline
FR4 & QR Code Generation: Users must be able to generate and view a QR code that links to their specific deck. \\
\hline
FR5 & Promotional Vouchers: The system must allow users to request and receive promotional voucher codes. \\
\hline
FR6 & Deck Analytics: Users must be able to generate and view statistical charts, such as a mana curve plot, for their decks. \\
\hline
FR7 & AI Suggestions: The system must provide AI-driven card recommendations to help users improve their deck compositions. \\
\hline
\end{tabular}
\label{tab1}
\end{center}
\end{table}

\begin{table}[htbp]
\caption{Non-Functional Requirements}
\begin{center}
\begin{tabular}{|c|p{0.85\linewidth}|}\hline
 \multicolumn{2}{|c|}{\textbf{System Quality Attributes}}\\\hline 
\hline
\textbf{ID} & \textbf{Requirement Description} \\
\hline
NFR1 & Scalability: The application infrastructure must automatically scale up or down based on fluctuating user traffic. \\
\hline
NFR2 & Performance: Database queries must execute with single-digit millisecond latency to ensure a highly responsive user interface. \\
\hline
NFR3 & Security: User data, external API keys, and database credentials must be strictly secured and managed. \\
\hline
NFR4 & Reliability: The core Django application must remain operational and degrade gracefully even if external third-party services fail. \\
\hline
NFR5 & Maintainability: The system must utilize a decoupled microservice architecture, allowing independent deployment of background tasks. \\
\hline
\end{tabular}
\label{tab2}
\end{center}
\end{table}

# Section 3: Architecture and Design Aspects

The architecture of AetherFlow was designed to be a decoupled, cloud-native microservice model, allowing scaling and smooth integration of third-party web services. While a monolithic application is easy to develop it can get very complex and difficult to scale up as the application grows [1]. Breaking the project into microservices allow each service to evolves separately, enabling the use of distinct architectures, platforms, and technology while it can be managed, deployed, and scaled independently [2]. This approach added some complexity in how the parts communicate to each other, but it was necessary to make the application resilient, if one piece fails, it doesn’t bring down the whole website. Figure 1 illustrates the application design.

![Figure 1: AetherFlow Complete System Architecture Diagram](path/to/your/main_architecture_diagram.png)

## 3.1 Web Hosting and Auto-Scaling

The core Django application is deployed on AWS Elastic Beanstalk, a managed service that facilitates the deployment of web applications across different platforms. While developers provide the application code, the service automatically handles the underlying infrastructure, provisioning EC2 instances, load balancing, health monitoring, and dynamic scaling of the environment [3].

This application could have been deployed directly onto an EC2 instance, which would offer complete control over the server environment. However, managing an EC2 instance manually would be more complex because developers are responsible for load balancing, software patching, and scaling the server if traffic increases. A significant benefit of using Elastic Beanstalk is its automatic Auto-Scaling capabilities; by monitoring metrics like CPU usage, it can automatically create additional servers during busy periods. The trade-off is that developers have reduced control to modify the underlying server configuration compared to a complex container system like Kubernetes [4]. For this project, the ease of setup and reliable horizontal scaling made Elastic Beanstalk the optimal choice.

## 3.2 Event-Driven Serverless Microservices

Instead of the main application handling heavy or long-running tasks, specific microservices were created and deployed to AWS Lambda to prevent them from slowing down the primary server. A microservices architecture breaks down an application into small, independent services that can be deployed, scaled, and managed autonomously [2]. By adopting this approach for specific background tasks, the application benefits from increased fault tolerance, scalability improvements, ease of deployment, and optimized resource usage without compromising the primary server [5].

As illustrated in Figure 1, this event-driven architecture directly supports two core background features:

1.  **QR Code Generation Service:** A custom AWS Lambda function processes incoming REST requests via Amazon API Gateway to generate QR codes from deck URLs.
2.  **Scryfall Card Sync Service:** An independent background Lambda function is triggered weekly via Amazon EventBridge to download bulk MTG card data directly into an S3 bucket, implementing a scheduled cron job pattern in the cloud.

**Critical Analysis & Justification:**
By utilizing serverless computing, it became possible to run these background services without the overhead of managing, scaling, or provisioning the underlying servers. The AWS infrastructure automatically manages usage spikes, ensuring that sudden high traffic does not crash the system [6]. The trade-off for offloading these tasks is the introduction of network latency and "cold starts"—a brief delay that occurs when a serverless function is invoked after being idle. However, because the Scryfall Sync runs as a scheduled background job, latency is irrelevant. For the QR code generator, the fractional delay of a cold start is vastly outweighed by the cost-effectiveness and infinite scalability gained by not maintaining a dedicated, always-on server to process images.

## 3.3 Databases and Storage Strategy

Instead of attempting to consolidate all project data into a single database structure, a separated approach for database systems and file storage was implemented. This involved using different systems specifically tailored to the type of data being stored. While managing multiple systems increases the project's complexity by requiring different connection methods, this trade-off allowed for the use of the most efficient tool for each specific job.

### 3.3.1 AWS DynamoDB (NoSQL for Unstructured Data)
Amazon DynamoDB is a serverless, distributed NoSQL database that delivers single-digit performance at any scale. The use of a NoSQL database for storing Magic: The Gathering (MTG) user's decks shows significant architectural advantages. Due to its flexible schema, it can adapt to varied card attributes, ensuring low latency data retrieval as the user base grows.

*Critical Analysis:* For this project, AWS DynamoDB was chosen. Because it is a NoSQL managed database, it can store complete deck structures efficiently using a single-table key-value design. This choice is justified because DynamoDB provides highly predictable, single-digit millisecond response times regardless of how large the database grows, which is a critical performance requirement for a snappy, responsive deck builder application. However, this NoSQL approach also introduces drawbacks. The lack of standard query optimization makes it difficult to execute complex analytical queries efficiently. For example, a query that requires scanning the full table can be very slow and expensive. Additionally, because DynamoDB does not support traditional relational indexing, it can be difficult to find specific subsets of nested items in a large table without significant upfront data modeling. In conclusion, while DynamoDB is a powerful database solution for high-speed CRUD operations, these trade-offs highlight the necessity of the multi-database strategy.

### 3.3.2 Supabase / PostgreSQL (Relational Data)
Because this project was built with Django, it provides a strong and straightforward authentication system. This authentication system utilizes relational data structures to store user profiles, session cookies, and passwords securely [10]. 

*Critical Analysis:* To handle Django’s relational database requirements, Supabase was chosen for this project. Supabase is a serverless, open-source backend service that provides a highly scalable PostgreSQL relational database [11]. This choice is justified because this will enable the application to take advantage of Django’s rich built-in authentication functionality without the need of manually provisioning or managing a traditional SQL server.

### 3.3.3 AWS S3 (Object Storage)
For this application, S3 is utilized specifically to store large binary and image files, particularly the dynamically generated QR code images and the massive bulk MTG card JSON files downloaded weekly by the cron job (Scryfall Card Sync Service). 

*Critical Analysis:* To handle these large, unstructured files, Amazon S3 was chosen for this project. Amazon S3 is an object storage service that offers scalability, security, and performance [12]. While S3 provides reliable object storage, if the bucket is not adequately secured, it can be susceptible to unauthorized access [13]. Securing the bucket requires complex Identity and Access Management (IAM) policies to ensure private data remains secure while necessary images remain publicly accessible. Despite this complexity, for the specific task of handling massive bulk data and images, S3 remains the most efficient architectural choice.
---

# Section 4: Implementation and Web Service Integration

The implementation phase of AetherFlow centered on constructing the reliable Django core and subsequently authoring independent service modules to consume a required mix of external Application Programming Interfaces (APIs). The success of the application hinges on the successful integration of five distinct web services, fulfilling the project requirements by bringing together self-authored, classmate-authored, and public APIs into a cohesive user experience.

## 4.1 Custom QR Code Service (Self-Developed API)

To satisfy the project requirements of consuming a web service developed for this project, the core Django application integrates with a custom microservice that was developed and deployed as an AWS Lambda function, and securely exposed as a RESTful endpoint via Amazon API Gateway. The benefit of using this approach is that services implemented as RESTful APIs are scalable, flexible, and independent [14]. Because the service is completely decoupled from the main application, it can independently scale up or down to handle traffic—especially during peak QR code generation—without degrading the performance of the main application. To support integration and ensure the service can be easily utilized by other developers, comprehensive API documentation was created and is publicly hosted at https://heroic-nougat-c67308.netlify.app/#quick-start.

The application constructs a JSON payload containing the target URL and sends it to the API Gateway. This triggers the Lambda function to generate the actual QR code. Once the image is created, the function saves it to an Amazon S3 bucket, records the details in a DynamoDB table, and sends back a pre-signed URL. From there, the Django application downloads the image using that temporary link and converts it behind the scenes so it can be displayed directly on the user’s screen.

```python
class QRService:
    @staticmethod
    def get_qr_code_url(deck_id, deck_url):
        qr_endpoint = os.getenv("QR_CODE_ENDPOINT")
        if not qr_endpoint:
            raise Exception("QR_CODE_ENDPOINT not set")

        payload = {"deck_id": str(deck_id), "url": deck_url}
        response = requests.post(qr_endpoint, json=payload, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            qr_url = data.get("qrcode_image_url") or data.get("url")

            if qr_url and qr_url.startswith("https"):
                img_response = requests.get(qr_url, timeout=10)
                if img_response.status_code == 200:
                    img_b64 = base64.b64encode(img_response.content).decode("utf-8")
                    content_type = img_response.headers.get("Content-Type", "image/png")
                    return f"data:{content_type};base64,{img_b64}"
            return qr_url
        else:
            raise Exception(f"Service returned {response.status_code}")
```

This entire flow provides a seamless experience for the user while successfully demonstrating the integration of a custom, cloud-native microservice.

## 4.2 Voucher Verification API (Classmate Developed)

To fulfill the project requirement of integrating a peer-developed web service, AetherFlow consumes an external REST endpoint created by a classmate. This integration allows users to request promotional codes that can be applied to their accounts. The comprehensive API documentation for this service can be found at https://app.swaggerhub.com/apis/student-c67-be7/api-safetrade-voucher/1.0.0. Similar to the QR service, this external dependency is completely decoupled from the main application, ensuring that any downtime or latency on the external service does not crash the core Django platform.

Within the `deck_builder/services/voucher_service.py` module, the application sends a POST request with an empty JSON body to the external API's endpoint. The service handles the network request and explicitly catches potential timeout exceptions to prevent the application from hanging if the external service is unavailable. Because the external API returns a plain text block rather than structured JSON, the application aggressively parses the returned text using Python regular expressions to extract the unique Voucher ID, which is then dynamically attached to the user's view context.

```python
class VoucherService:
    @staticmethod
    def generate_voucher():
        url = os.environ.get("VOUCHER_SERVICE_ENDPOINT")
        if not url:
            logger.error("VOUCHER_SERVICE_ENDPOINT environment variable not set")
            return None

        try:
            response = requests.post(url, json={}, timeout=10)
            response.raise_for_status()
            response_text = response.text

            match = re.search(r"voucher ID is '([^']+)'", response_text)
            if match:
                return match.group(1)
            else:
                logger.error(f"Could not extract voucher ID: {response_text}")
                return None

        except requests.RequestException as e:
            logger.error(f"Error calling Voucher API: {str(e)}")
            return None
```

By carefully catching errors and pulling out exactly the text it needs, the application ensures that users won't experience sudden crashes or freezing, even if the external service behaves unpredictably.

## 4.3 Analytical Plotting API (Classmate Developed)

To further fulfill the project requirement of integrating a peer-developed web service, AetherFlow consumes the external FileConvert API created by a classmate to validate user deck compositions by generating statistical visual representations of a deck's "mana curve". Comprehensive documentation for this external API was referenced at https://fileapi.arijitdeb.com/#home to properly implement the integration.

Within the `deck_builder/services/plot_service.py` module, the application executes a complex three-step orchestration process to successfully generate the image. First, the application calculates the deck's mana statistics and generates an in-memory CSV string. Next, it sends a GET request to the FileConvert API to receive a secure, pre-signed Amazon S3 upload URL. The application then executes an HTTP PUT request to upload the raw CSV data directly to the classmate's S3 bucket. Finally, the service sends a POST request to the `/ConvertData/` endpoint to trigger the actual plot generation, supplying the URL of the newly uploaded data. Once the external service finishes processing the numbers, it sends back a link to the finished PNG graph, which Django then displays straight on the user's deck analysis page.

```python
class PlotService:
    @classmethod
    def _generate_plot(cls, data_url, plot_type="bar"):
        """Step 3: Call the ConvertData endpoint to generate a plot."""
        base_url = cls._fileconvert_base_url()
        endpoint = f"{base_url}/ConvertData/"

        response = requests.post(
            endpoint,
            json={
                "data_url": data_url,
                "action": "plot",
                "plot_type": plot_type
            },
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        response.raise_for_status()

        payload = response.json()
        if "url" not in payload:
            raise ValueError("ConvertData response missing 'url'")
        return payload.get("url")
```

This step-by-step approach shows how the application can smoothly pass data between completely separate cloud services to build complex features.

## 4.4 Google Gemini AI (Public API)

To give players smart, AI-driven advice on how to improve their decks, AetherFlow connects with the Google Gemini API. This is handled using the official `google-genai` Python library, which lets the application easily talk to Google's powerful generative models. 

Inside the `card_recommender/services/ai_recommender.py` file, the application takes a list of the cards currently in the user's deck, builds a short, specific prompt, and asks Gemini to recommend three new cards that would make the deck stronger. It specifically asks Gemini to return the answer as raw JSON data. When Gemini replies, the application carefully strips away any extra formatting or markdown to safely extract just the recommended card names. 

```python
class DeckRecommendationAgent:
    def get_deck_improvement_recommendations(self, deck_cards, format_name="standard"):
        # ...setup api client and build deck_list string...
        prompt = (
            f"Analyze this {format_name} MTG deck: {deck_list}. "
            "Recommend 3 cards to improve synergy, fill gaps, or strengthen strategy. "
            "Cards must be legal in the format and complement the deck's theme. "
            "Return ONLY raw JSON, no markdown, no explanation. "
            'JSON format: {"cards": ["Card Name", "Card Name", "Card Name"]}'
        )

        try:
            response = self._client.models.generate_content(
                model="gemini-2.5-flash", contents=prompt, config=generation_config
            )
            response_text = self._get_response_text(response)
            return self._parse_recommendations(response_text)
        except Exception as e:
            print(f"DeckRecommendationAgent: AI generation failed. Error: {e}")
            return []
```

This approach allows the application to leverage complex AI logic while hiding all the messy string-parsing math from the end user, presenting them with a clean, helpful list of suggestions.

## 4.5 Scryfall API (Public REST API)

For a Magic: The Gathering application, having accurate card data is essential. The project relies on the widely used Scryfall API as its ultimate source of truth. However, asking the Scryfall API for every single card individually during a user search would be incredibly slow and would quickly hit their rate limits.

Instead of constantly pinging the live API, AetherFlow uses a smart architectural pattern. A background AWS Lambda function operates as a weekly cron job, completely detached from the main application. Once a week, this Lambda function securely connects to the Scryfall API, downloads their massive bulk data file containing up-to-date card information, and saves it directly to a dedicated Amazon S3 bucket.

Then, when a user searches for a card, the application itself simply reads from that massive S3 file, caches it, and builds a lightning-fast local lookup index.

If a card has a strange spelling or is genuinely missing from the weekly S3 snapshot, it has a built-in safety net. It will gracefully fall back to making an isolated, live HTTP request to the Scryfall API as a last resort:

```python
        try:
            self._api_fallback_count += 1
            # Scryfall requests 50-100ms delay between requests (max 10/sec)
            time.sleep(0.1)
            resp = requests.get(
                "https://api.scryfall.com/cards/named",
                params={"fuzzy": name},
                timeout=5,
            )
            if resp.status_code == 200:
                card_data = resp.json()
                # Cache it for future lookups
                index[name_lower] = card_data
                return card_data
        except Exception as e:
            logger.warning(f"Scryfall API fallback failed for '{name}': {e}")
```

By relying heavily on the automated S3 sync and only using the live API as an occasional backup, AetherFlow guarantees that card searches remain incredibly fast, responsive, and respectful of public rate limits, even under heavy user load.

# Section 5: Continuous Integration, Delivery, and Deployment

AetherFlow uses a fully automated CI/CD pipeline orchestrated via GitHub Actions (`.github/workflows/CI.yml`). It is divided into two phases: Testing and Deployment. 

The Testing phase initializes a Python environment, installs dependencies, and runs `python manage.py check` as a quality gate to prevent broken code from reaching production. If testing succeeds, the Deployment phase securely injects AWS IAM credentials via GitHub Secrets, dynamically updates server environment variables in the Elastic Beanstalk environment (`AetherFlow-env`), packages the application into a ZIP file, and deploys it using `beanstalk-deploy`. This ensures seamless roll-outs to the active EC2 instances without manual intervention.

# Section 6: Conclusions and Findings

The AetherFlow project successfully demonstrates a scalable, cloud-native application integrating completely decentralized web services while satisfying all requirements. Important findings emphasize the necessity of robust error handling for third-party APIs, such as graceful fallbacks and local caching. Furthermore, a strategic multi-database approach—DynamoDB for NoSQL flexibility, Supabase for relational authentication, and S3 for heavy object storage—proved vastly superior to forcing a monolithic database architecture.

## 6.1 Personal Reflection

Building this project provided profound insights into modern cloud engineering. Transitioning to a distributed AWS ecosystem (Elastic Beanstalk, Lambda, API Gateway) was challenging, especially managing cross-origin resource sharing (CORS) and complex GitHub Actions pipelines. However, seeing separate microservices seamlessly interact—like a serverless Lambda generating QR codes without slowing the main Django server—was incredibly rewarding. It reinforced the understanding that true scalability relies heavily on intelligent architecture, efficient caching strategies, and robust automation.
