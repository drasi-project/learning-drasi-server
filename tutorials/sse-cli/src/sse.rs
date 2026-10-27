// Copyright 2026 The Drasi Authors.
// Licensed under the Apache License, Version 2.0.

#[derive(Default)]
pub struct Decoder {
    line: Vec<u8>,
    data: Vec<String>,
    after_cr: bool,
    started: bool,
}

impl Decoder {
    pub fn push(
        &mut self,
        bytes: &[u8],
        debug: bool,
        mut on_event: impl FnMut(&str) -> Result<(), String>,
    ) -> Result<(), String> {
        for &byte in bytes {
            if self.after_cr && byte == b'\n' {
                self.after_cr = false;
                continue;
            }
            self.after_cr = byte == b'\r';
            if matches!(byte, b'\r' | b'\n') {
                let line = String::from_utf8(std::mem::take(&mut self.line))
                    .map_err(|error| format!("Invalid UTF-8 in SSE stream: {error}"))?;
                let line = if self.started {
                    line.as_str()
                } else {
                    self.started = true;
                    line.strip_prefix('\u{feff}').unwrap_or(&line)
                };
                if line.is_empty() {
                    if !self.data.is_empty() {
                        let data = std::mem::take(&mut self.data).join("\n");
                        on_event(&data)?;
                    }
                } else {
                    let (field, value) = line.split_once(':').unwrap_or((line, ""));
                    let value = value.strip_prefix(' ').unwrap_or(value);
                    if field == "data" {
                        self.data.push(value.to_owned());
                    } else if debug {
                        eprintln!("[sse] {line}");
                    }
                }
            } else {
                self.line.push(byte);
            }
        }
        Ok(())
    }

    pub fn finish(&self) -> Result<(), String> {
        if !self.line.is_empty() || !self.data.is_empty() {
            return Err("SSE stream ended with an incomplete event".into());
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn handles_every_byte_boundary_and_sse_line_ending() {
        for ending in ["\n", "\r\n", "\r"] {
            let wire = [
                "\u{feff}: keep-alive",
                "event: snapshot",
                "id: 42",
                "retry: 1000",
                "unknown: ignored by SSE",
                "data: {",
                "data: \"message\": \"café ☕\"}",
                "",
                "data:{\"next\":true}",
                "",
                "",
            ]
            .join(ending);
            for split in 0..=wire.len() {
                let mut decoder = Decoder::default();
                let mut events = Vec::new();
                for chunk in [&wire.as_bytes()[..split], &wire.as_bytes()[split..]] {
                    decoder
                        .push(chunk, false, |data| {
                            events.push(data.to_owned());
                            Ok(())
                        })
                        .unwrap();
                }
                decoder.finish().unwrap();
                assert_eq!(events, ["{\n\"message\": \"café ☕\"}", "{\"next\":true}"]);
            }
        }
    }

    #[test]
    fn waits_for_blank_line_and_keeps_data_whitespace() {
        let mut decoder = Decoder::default();
        decoder
            .push(b"data:  one \ndata\ndata: three\n", false, |_| {
                panic!("event is not complete")
            })
            .unwrap();
        assert!(decoder.finish().is_err());
        let mut events = Vec::new();
        decoder
            .push(b"\n", false, |data| {
                events.push(data.to_owned());
                Ok(())
            })
            .unwrap();
        assert_eq!(events, [" one \n\nthree"]);
        decoder.finish().unwrap();
    }

    #[test]
    fn rejects_invalid_utf8_and_propagates_consumer_errors() {
        assert!(Decoder::default()
            .push(b"data: \xff\n\n", false, |_| Ok(()))
            .unwrap_err()
            .contains("UTF-8"));
        assert_eq!(
            Decoder::default()
                .push(b"data: {}\n\n", false, |_| Err("write failed".into()))
                .unwrap_err(),
            "write failed"
        );
        let mut decoder = Decoder::default();
        decoder.push(b"data: {", false, |_| Ok(())).unwrap();
        assert!(decoder.finish().is_err());
    }
}
