# Lambda setup (render in the cloud)

One-time, about 20 minutes. The user needs an AWS account with a card on it
(aws.amazon.com, **Create an AWS account**). Every render after this costs a few cents to a few
dollars, depending on length. Claude quotes each one before it runs.

Do the AWS console steps with the user, one at a time. They click; you tell them where.

Run the `npx` commands from `~/.ai-video-editor/remotion` (the renderer must be installed first,
setup step 4).

## 1. A permission policy for the renderer

```bash
cd ~/.ai-video-editor/remotion && npx remotion lambda policies role
```

It prints a block of JSON. In the AWS console:
1. Search **IAM**, open it, then **Policies** > **Create policy**.
2. Switch to the **JSON** tab, delete what is there, paste the block.
3. **Next**, name it exactly `remotion-lambda-policy`, **Create policy**.

## 2. A role that uses it

1. **IAM** > **Roles** > **Create role**.
2. Trusted entity: **AWS service**, use case: **Lambda**. **Next**.
3. Tick `remotion-lambda-policy`. **Next**.
4. Name it exactly `remotion-lambda-role`. **Create role**.

The names must match exactly. The renderer looks for them.

## 3. A user for this computer

1. **IAM** > **Users** > **Create user**. Name: `remotion-user`. No console access. **Next**,
   **Next**, **Create user**.
2. Open `remotion-user` > **Permissions** > **Add permissions** > **Create inline policy** >
   **JSON**. Paste the output of:
   ```bash
   cd ~/.ai-video-editor/remotion && npx remotion lambda policies user
   ```
   Name it `remotion-user-policy`, **Create policy**.
3. **Security credentials** tab > **Create access key** > **Application running outside AWS** >
   **Next** > **Create access key**. Leave that page open.

## 4. Save the key

**Never ask for the key in the chat.** The user runs this in their own terminal window, not here:

```bash
python3 <setup skill folder>/scripts/setup.py awskey
```

(`py` on Windows.) It asks for the access key ID, the secret (hidden as they type) and a region.
`us-east-1` is fine unless they want one closer to them. The key is saved to
`~/.ai-video-editor/aws.env`, readable only by them.

## 5. Check

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/setup.py" lambda
```

Every line should read as passing. A failure names the missing permission: re-check the policy
JSON from step 1 or 3.

## 6. First render

Pick **Lambda** at render time. The first Lambda render also creates the renderer function and a
storage bucket in their account (a minute, once). It prints the real cost at the end.

## Costs and cleanup

- Renders: pay per second of compute. The render prints the real cost.
- Storage: rendered files sit in an S3 bucket named `remotionlambda-...`. Pennies a month. Empty it
  in the S3 console to stop that.
- To remove everything: `npx remotion lambda functions rmall` and delete the bucket in S3.
