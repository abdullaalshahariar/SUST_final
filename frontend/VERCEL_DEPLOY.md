# Deploy the frontend to Vercel

This directory is a plain static HTML/CSS/JavaScript site. It calls the API at
`https://sust-final.onrender.com` when deployed, and `http://127.0.0.1:8000`
when opened locally.

In Vercel, import the same Git repository and set **Root Directory** to
`frontend`. Use the **Other** framework preset, with no build command and no
output directory. Deploy the project.

After the first deployment, push the backend CORS change in this repository
and redeploy the Render backend. Vercel preview and production domains ending
in `.vercel.app` are then allowed to call the API.

The deployed site opens `index.html`, which redirects to `login.html`.
