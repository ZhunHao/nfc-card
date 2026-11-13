# NFC tag content

Each card's tag holds **one NDEF URI record**, e.g. `https://example.com/nfc/orbit`, pointing
at a path on a domain you control. Redirect that path (a 302, so browsers don't cache it) to
wherever the card should go; the destination can then change after the cards are handed out
without rewriting any tag.

- The tag content is static: U1's SDA, SCL and FD pins are unconnected, so the ATtiny can't
  write the tag or see taps. Content is written once from a phone.
- A vCard can't be updated after the card is given away; a redirect can.
- The URI is well under the 888-byte NDEF area of the 1k NT3H2111.
- If the domain lapses, every card's link dies, so keep auto-renew on.
- **Don't permanently lock the tags.** Use the NTAG's 32-bit password instead (AUTH0 sets the
  first protected page; `NFC_PROT = 0b` means only writes need the password, so phones still
  read without one). Keep the password; it's the only way to rewrite the card later.

## Writing a tag

1. Program and test the MCU first (`firmware/README.md`).
2. **Format the blank tag.** The NT3H2111 ships with its capability container at `00000000h`
   (datasheet §8.3.10), so iOS TagWriter says "Tag is not NDEF compliant" and NFC Tools says
   "not supported". In NFC Tools (WAKDEV) → Other → Advanced NFC commands, send:
   ```
   A2 03 E1 10 6D 00    → 0A
   A2 04 03 00 FE 00    → 0A
   30 03                → E1 10 6D 00 03 00 FE 00 …  (check)
   ```
   The CC cannot be cleared from NFC afterwards, and the last byte of the first command must be
   `00`; `0F` makes the tag read-only for good.
3. Write one URI record (NFC Tools: Write → URL, 30 bytes; or TagWriter: Website, URI type
   `https://`, data `example.com/nfc/orbit`).
4. Tap with an iPhone (card flat on the back, near the camera) and an Android phone; both
   should open the site.
5. Set the write password. Confirm the app you use writes AUTH0/PWD with `NFC_PROT = 0b`
   (write-protect only), then check a phone still reads it and a write without the password fails.
