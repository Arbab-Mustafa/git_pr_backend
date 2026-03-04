# Quick Fix: Add Environment Variables to Vercel
# Run these commands one by one

# 1. Navigate to backend directory
cd backend

# 2. Add GROQ_API_KEY (you'll be prompted to paste your key)
vercel env add GROQ_API_KEY production

# 3. Add other variables (you'll be prompted for each value)
vercel env add GROQ_MODEL production
# When prompted, enter: llama-3.3-70b-versatile

vercel env add ALLOWED_ORIGINS production
# When prompted, enter: chrome-extension://*

vercel env add DEBUG production
# When prompted, enter: false

# 4. Redeploy with new environment variables
vercel --prod

# That's it! After deployment completes, test your extension again.
