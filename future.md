# Future Roadmap: Refining the Iterative Process

As an artist-first tool, this AI generator is designed to go beyond the traditional "slot-machine" approach of text-to-image. The goal is to provide a true "workshopping" canvas for creative ideas.

Here are the brainstormed ideas for future phases once the Cloud deployment is stable:

## 1. The Regional Editor (Inpainting)
* **What it is:** The ability to regenerate a specific part of an image while preserving the rest (e.g., fixing a weird hand, or changing the color of a shirt).
* **Implementation Idea:** A "Touch Up" button on the UI that opens an HTML Canvas. The user paints a "mask" over the area they want changed, types a new prompt specific to that area, and the backend processes an inpainting request.

## 2. Style & Concept Mixing (Image Prompting)
* **What it is:** The ability to use multiple input images to define both the subject and the stylistic aesthetic perfectly.
* **Implementation Idea:** A new panel for "Image Inputs" where the user can drop multiple images and assign them weights or roles (e.g., "Use Image A for the character subject, and Image B for the watercolor style").

## 3. Prompt Branching (The Idea Tree)
* **What it is:** Transforming the linear Generation Queue into an interactive, visual flowchart.
* **Implementation Idea:** When "workshopping" an idea, a user often wants to explore two different directions (e.g., "what if it was raining" vs "what if it was snowing"). A node-based UI (like React Flow) would allow the user to see exactly how an image evolved, and click any historical image to spawn a new branch of variations, keeping creative exploration perfectly organized.

## 4. Multi-User Authentication & SaaS Readiness
* **What it is:** Before public launch, the system needs to sandbox generated sessions so users cannot see each other's work.
* **Implementation Idea:** Add Firebase or Clerk authentication. Update `sessions.json` to map to `user_id` -> `session_id`, and migrate the `static/outputs/` directory to an Amazon S3 or Cloudflare R2 bucket to prevent local server disk exhaustion.

## 5. Rate Limiting protection
* **What it is:** Protecting the expensive Cloud API keys from bot abuse on the public internet.
* **Implementation Idea:** Add a Flask middleware or use `Flask-Limiter` to enforce a strict generation limit (e.g., "5 free images per IP address per hour").
