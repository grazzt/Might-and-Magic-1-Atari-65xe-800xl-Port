; ZX0 (v2) decoder spike. In: src = compressed stream, dst = destination.
; Zero page: src dst off m bitbuf mp tmp (12 bytes). Y is 0 throughout.
        .export zx0, zx0_end
        .exportzp src, dst
src     = $F8
dst     = $FA
off     = $FC           ; 16-bit, dst + off = match source
m       = $FE           ; running length, kept complemented: m = ~value
mlo     = m
mhi     = m+1
bitbuf  = $E8
mp      = $E9
tmpl    = $EB
tmph    = $EC

        .org $0800
zx0:
        lda #$FF
        sta off
        sta off+1
        lda #$80
        sta bitbuf
        ldy #0
lit:    jsr gamma
lcopy:  jsr getsrc
        sta (dst),y
        inc dst
        bne :+
        inc dst+1
:       jsr step
        bne lcopy
        jsr getbit
        bcs newoff
rep:    jsr gamma
match:  clc
        lda dst
        adc off
        sta mp
        lda dst+1
        adc off+1
        sta mp+1
mcopy:  lda (mp),y
        sta (dst),y
        inc mp
        bne :+
        inc mp+1
:       inc dst
        bne :+
        inc dst+1
:       jsr step
        bne mcopy
        jsr getbit
        bcc lit
newoff: jsr gamma
        lda mhi
        cmp #$FE
        beq zx0_end             ; length 256: end marker
        lda mlo
        eor #$FF                ; msb
        lsr a
        sta tmph
        lda #0
        ror a
        sta tmpl                ; tmp = msb << 7
        jsr getsrc
        pha
        lsr a
        sec
        sbc tmpl
        sta off
        lda #0
        sbc tmph
        sta off+1
        ldx #$FF
        stx mhi
        dex
        stx mlo
        pla
        lsr a                   ; carry: first bit of the length code
        jsr gamma_c
        lda mlo                 ; one more byte than the code says
        bne :+
        dec mhi
:       dec mlo
        jmp match

; m = ~value. Count one byte done; Z set when all are (m = $FFFF).
step:   inc mlo
        bne :+
        inc mhi
:       lda mlo
        and mhi
        eor #$FF
        rts

gamma:  ldx #$FF
        stx mhi
        dex
        stx mlo
g_more: jsr getbit
gamma_c:
        bcs zx0_end             ; (shared rts)
        jsr getbit              ; raw data bit shifts into ~value as is
        rol mlo
        rol mhi
        jmp g_more
getsrc: lda (src),y
        inc src
        bne :+
        inc src+1
:       rts
getbit: asl bitbuf
        bne :+
        jsr getsrc
        rol a
        sta bitbuf
:
zx0_end:
        rts
