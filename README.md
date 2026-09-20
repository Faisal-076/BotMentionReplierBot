# 🤖 Telegram Guest Mode & Multi-Bot Replier | Control Center

একটি উচ্চগতির পাইথন টেলিগ্রাম বট ক্লাস্টার এবং মডার্ন ডার্ক-মোড **Web UI Control Center**, যা কোনো গ্রুপে **সদস্য (Member) বা অ্যাডমিন (Admin) না হয়েও** টেলিগ্রামের অফিসিয়াল **Guest Mode** (`guest_message` এবং `answerGuestQuery`) ব্যবহার করে স্বয়ংক্রিয়ভাবে মেনশনের কোট-রিপ্লাই দিতে পারে।

ব্রাউজার থেকেই সরাসরি বট টোকেন যোগ/রিমুভ করা, রিপ্লাই টেমপ্লেট এডিট করা, লাইভ অ্যাক্টিভিটি লগ দেখা এবং ক্লাস্টার চালু/বন্ধ করা যায়।

---

## 🌟 প্রধান বৈশিষ্ট্যসমূহ (Key Features)

- **🌐 Modern Web UI Dashboard:** ব্রাউজার থেকেই সিঙ্গেল বা মাল্টিপল বট টোকেন ম্যানেজ ও লাইভ ভেরিফিকেশন।
- **💬 Interactive Template Editor:** `{first_name}`, `{username}`, `{bot_name}`, `{chat_title}`, `{date}` ভেরিয়েবল চিপস সহ রিয়েল-টাইম টেমপ্লেট কাস্টমাইজেশন।
- **📜 Live Mention Stream:** টার্মিনাল ছাড়াই ড্যাশবোর্ডে লাইভ মেনশন এবং রেসপন্স ট্র্যাকিং।
- **🚀 Ultra-Fast Latency Engine:** TCP Connection Pooling এবং In-Memory DNS Caching—যা রিকোয়েস্ট ল্যাটেন্সি প্রায় ৫০% কমিয়ে দেয়।
- **🐳 Northflank & Docker Ready:** ফ্রাঙ্কফুর্ট (Europe) ক্লাউডে ২৪/৭ ফ্রি প্ল্যানে চালানোর জন্য সম্পূর্ণ তৈরি।

---

## 💻 লোকাল কম্পিউটারে চালানো (Local Setup)

### ১. ডিপেনডেন্সি ইনস্টল:
```bash
pip install -r requirements.txt
```

### ২. Web UI Control Center চালু করুন:
```bash
python main.py dashboard
```
ব্রাউজারে ওপেন করুন: **`http://localhost:8000`**

ড্যাশবোর্ড থেকেই আপনি:
- নতুন বটের টোকেন যোগ করতে পারবেন।
- টেলিগ্রাম সার্ভার থেকে Guest Mode অন আছে কিনা তা **Verify** করতে পারবেন।
- রিপ্লাই টেক্সট ও সেটিংস পরিবর্তন করতে পারবেন।
- **Start / Stop / Restart** বাটনে চাপ দিয়ে বট নিয়ন্ত্রণ করতে পারবেন।

---

## 🚀 Northflank-এ ফ্রি ২৪/৭ ডিপ্লয়মেন্ট গাইড (Northflank Hosting)

টেলিগ্রামের মাদার ডেটাসেন্টারের পাশে **ফ্রাঙ্কফুর্ট (Frankfurt)** রিজিয়নে ০.১ সেকেন্ড স্পিডে ২৪/৭ চালানোর নিয়ম:

1. **GitHub-এ প্রজেক্ট রাখুন:**
   আপনার GitHub অ্যাকাউন্টে এই প্রজেক্টটি পুশ করা আছে।

2. **Northflank-এ লগইন করুন:**
   [northflank.com](https://northflank.com)-এ যান এবং সাইন-আপ/লগইন করুন।

3. **Create Service:**
   - ড্যাশবোর্ড থেকে **Create Service** > **Deployment Service** বেছে নিন।
   - **Service Name:** `mention-replier-bot` দিন।
   - **Repository:** আপনার GitHub কানেক্ট করে `BotMentionReplierBot` রিপোজিটরিটি সিলেক্ট করুন।
   - **Branch:** `main` সিলেক্ট করুন।
   - **Build Type:** `Dockerfile` অটোমেটিক সিলেক্ট হবে।

4. **Region সিলেক্ট করুন (সবচেয়ে গুরুত্বপূর্ণ):**
   - Region হিসেবে সিলেক্ট করুন: **`Europe - West (Frankfurt)`**।
   *(কারণ টেলিগ্রামের সার্ভার ফ্রাঙ্কফুর্টে থাকায় পিং ল্যাটেন্সি হবে মাত্র ১-২ মিলিসেকেন্ড!)*

5. **Environment Variables সেট করুন:**
   Northflank-এর **Environment** ট্যাবে গিয়ে নিচের ভেরিয়েবলগুলো বসান:
   - `BOT_TOKENS`: আপনার টেলিগ্রাম বটের টোকেন(গুলো)
   - `REPLY_MODE`: `both`
   - `PARSE_MODE`: `HTML`
   - `REPLY_DELAY`: `0.0`
   - `PORT`: `8000`

6. **Networking & Ports:**
   - Port: `8000`
   - Protocol: `HTTP`
   - Public Exposure: `Enabled` (এটি অন করলে আপনি নর্থফ্ল্যাঙ্কের একটি ফ্রি ডোমেন পাবেন, যা দিয়ে যেকোনো ডিভাইস বা মোবাইল থেকে Web UI অ্যাক্সেস করতে পারবেন!)

7. **Deploy:**
   - **Create & Deploy** বাটনে চাপ দিন। ১-২ মিনিটের মধ্যে আপনার বট লাইভ হয়ে যাবে এবং বিদ্যুৎ গতিতে ২৪/৭ কাজ করবে!

---

## 📂 প্রজেক্ট ফাইল আর্কিটেকচার (Architecture)

```text
p:/BotMentionReplierBot/
├── templates/
│   └── index.html         # আধুনিক ডার্ক-মোড Web UI ড্যাশবোর্ড
├── static/
│   ├── app.css            # গ্লাস মরফিজম ও ইন্টার ফন্ট সিএসএস
│   └── app.js             # রিয়েল-টাইম রিঅ্যাক্টিভ ফ্রন্টএন্ড ইঞ্জিন
├── dashboard_server.py    # FastAPI ব্যাকএন্ড ও কন্ট্রোল REST API
├── telegram_client.py     # অপটিমাইজড টেলিগ্রাম ক্লায়েন্ট (answerGuestQuery)
├── replier.py             # ডাইনামিক মেসেজ টেমপ্লেট ও হ্যান্ডলার
├── cluster.py             # মাল্টি-বট প্যারালাল ক্লাস্টার ইঞ্জিন
├── main.py                # প্রধান CLI (dashboard, run, verify, webhook)
├── Dockerfile             # নর্থফ্ল্যাঙ্ক ক্লাউড কন্টেইনার
├── .env                   # লোকাল কনফিগারেশন (গিটহাবে হাইড থাকবে)
├── .env.example           # কনফিগারেশন নমুনা
├── requirements.txt       # পাইথন লাইব্রেরি তালিকা
└── README.md              # পূর্ণাঙ্গ ডকুমেন্টেশন
```
