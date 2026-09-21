use super::*;
use crate::consts::P2PcztPoints;

impl PcztParser {
    /// Accepts optional coordinates only between an action's output header and
    /// ciphertext. They belong to this action and are discarded with its scratch state.
    pub fn parse_point_coordinates(
        &mut self,
        data: &[u8],
        ironwood: bool,
        points: P2PcztPoints,
    ) -> Result<(), ParserError> {
        let expected = if ironwood {
            PcztParserState::WaitIronwoodEncCiphertextLen
        } else {
            PcztParserState::WaitOrchardEncCiphertextLen
        };
        if self.state != expected {
            return Err(ParserError::from_sw(AppSW::BadState));
        }
        let kinds: &[bool] = match points {
            P2PcztPoints::Ephemeral => &[false],
            P2PcztPoints::Recipient => &[true],
            P2PcztPoints::Both => &[false, true],
        };
        if data.len() != 64 * kinds.len() {
            return Err(ParserError::from_sw(AppSW::WrongApduLength));
        }
        for (&recipient, coordinates) in kinds.iter().zip(data.chunks_exact(64)) {
            self.set_point_coordinates(coordinates, recipient)?;
        }
        Ok(())
    }

    fn set_point_coordinates(
        &mut self,
        coordinates: &[u8],
        recipient: bool,
    ) -> Result<(), ParserError> {
        let slot = if recipient {
            &mut self.current_action.recipient_point
        } else {
            &mut self.current_action.ephemeral_point
        };
        if slot.is_some() {
            return Err(ParserError::from_str("Duplicate PCZT point coordinates"));
        }
        let mut x = [0; 32];
        let mut y = [0; 32];
        x.copy_from_slice(&coordinates[..32]);
        y.copy_from_slice(&coordinates[32..]);
        let point = ValidatedPallasPoint::from_coordinates(x, y)
            .map_err(|_| ParserError::from_str("Invalid PCZT point coordinates"))?;
        if !recipient && !point.matches_encoding(&self.current_action.ephemeral_key) {
            return Err(ParserError::from_str("PCZT ephemeral point mismatch"));
        }
        *slot = Some(point);
        Ok(())
    }

    /// Bind supplied recipient coordinates even if IVK decryption succeeds or
    /// this is a dummy output, so an unused helper cannot escape validation.
    pub(super) fn check_output_recipient_point(&self) -> Result<(), ParserError> {
        if let Some(point) = &self.current_action.recipient_point {
            let mut encoded = [0; 32];
            encoded.copy_from_slice(&self.current_action.output_recipient[11..]);
            if !point.matches_encoding(&encoded) {
                return Err(ParserError::from_str("PCZT recipient point mismatch"));
            }
        }
        Ok(())
    }

    /// Reuses account material only after checking the complete cached path.
    /// The validation key is wiped before review; each real action still checks rk.
    pub(super) fn prepare_shielded_account_keys(
        &mut self,
        ctx: &mut PcztParserCtx<'_>,
        path: &Bip32Path,
    ) -> Result<(), ParserError> {
        let need_fvk = self.orchard_fvk.is_none();
        // This must run on cache hits too: a different account must fail closed.
        let sk = self
            .orchard_spending_key(path)
            .map_err(ParserError::from_sw)?;
        if need_fvk {
            let (fvk, ask) =
                derive_orchard_fvk_and_ask_from_sk(sk).map_err(ParserError::from_sw)?;
            ctx.tx_info.orchard_decipher_keys = Some(
                OrchardDecipherKeys::from_fvk(&fvk, orchard_network(path))
                    .map_err(ParserError::from_sw)?,
            );
            self.orchard_validation_key = Some(ask.ledger_validation_key());
            self.orchard_fvk = Some(fvk);
        }
        if ctx.tx_info.orchard_decipher_keys.is_none() || self.orchard_validation_key.is_none() {
            return Err(ParserError::from_sw(AppSW::BadState));
        }
        Ok(())
    }

    /// Returns recipient material only after matching a key from the checked account.
    /// The value is used immediately by the same action's nullifier check.
    pub(super) fn validated_spend_recipient(
        &self,
        fvk: &OrchardFvk,
        keys: &mut OrchardDecipherKeys,
    ) -> Result<Option<ledger_zcash_crypto::orchard::ValidatedRecipient>, ParserError> {
        let mut diversifier = [0u8; 11];
        diversifier.copy_from_slice(&self.current_action.spend_recipient[..11]);
        let mut claimed_pk_d = [0u8; 32];
        claimed_pk_d.copy_from_slice(&self.current_action.spend_recipient[11..]);
        let base = ledger_zcash_crypto::DiversifiedBase::derive(&diversifier)
            .map_err(|_| ParserError::from_str("Bad PCZT spend recipient"))?;
        for scope in [OrchardScope::External, OrchardScope::Internal] {
            let ivk = keys
                .incoming_viewing_key(fvk, scope)
                .map_err(ParserError::from_sw)?;
            if let Some(recipient) = ledger_zcash_crypto::orchard::ValidatedRecipient::from_ivk(
                ivk,
                &base,
                &claimed_pk_d,
            )
            .map_err(|_| ParserError::from_sw(AppSW::TechnicalProblem))?
            {
                return Ok(Some(recipient));
            }
        }
        Ok(None)
    }

    pub(super) fn parse_pczt_header(
        &mut self,
        reader: &mut ByteReader<'_>,
    ) -> Result<(), ParserError> {
        let mut magic = [0u8; 4];
        ok!(reader.read_exact(&mut magic));

        if &magic != MAGIC_BYTES {
            return Err(ParserError::from_str("Bad PCZT magic bytes"));
        }

        let version = ok!(reader.read_u32_le());
        if version != PCZT_VERSION_1 && version != PCZT_VERSION_2 {
            return Err(ParserError::from_str("Unsupported PCZT version"));
        }
        self.pczt_version = version;

        debug!("PCZT header: magic {:?}, version {}", magic, version);

        Ok(())
    }

    pub(super) fn parse_global(
        &mut self,
        ctx: &mut PcztParserCtx<'_>,
        reader: &mut ByteReader<'_>,
    ) -> Result<(), ParserError> {
        let tx_version_raw = ok!(reader.read_u32_le());
        let version_group_id = ok!(reader.read_u32_le());
        let branch_id_raw = ok!(reader.read_u32_le());

        let is_v5 = tx_version_raw == V5_TX_VERSION && version_group_id == V5_VERSION_GROUP_ID;
        let is_v6 = tx_version_raw == V6_TX_VERSION && version_group_id == V6_VERSION_GROUP_ID;

        if !is_v5 && !is_v6 {
            return Err(ParserError::from_str(
                "Unsupported PCZT transaction version",
            ));
        }

        let consensus_branch_id = ok!(BranchId::try_from(branch_id_raw));
        let fallback_lock_time = self.read_optional_u32(reader)?;
        let expiry_height = ok!(reader.read_u32_le());
        let coin_type = ok!(reader.read_u32_le());
        let tx_modifiable = ok!(reader.read_u8());

        if coin_type != ZCASH_BIP44_COIN_TYPE {
            return Err(ParserError::from_str("Unsupported PCZT coin_type"));
        }

        debug!(
            "PCZT global: version {}, version_group_id {:08x}, branch {:?}, fallback_lock_time {:?}, expiry_height {}, coin_type {}, tx_modifiable {:02x}",
            tx_version_raw,
            version_group_id,
            consensus_branch_id,
            fallback_lock_time,
            expiry_height,
            coin_type,
            tx_modifiable
        );

        if is_v5 {
            ctx.tx_info.tx_version = Some(TxVersion::V5);
        }
        ctx.tx_info.branch_id = Some(consensus_branch_id);
        ctx.tx_info.branch_id_raw = branch_id_raw;
        ctx.tx_info.locktime = fallback_lock_time.unwrap_or_default();
        ctx.tx_info.expiry_height = expiry_height;
        {
            ctx.tx_info.is_v6 = is_v6;
        }

        if is_v5 && self.pczt_version != PCZT_VERSION_1 {
            return Err(ParserError::from_str(
                "PCZT version 1 required for V5 transaction",
            ));
        }
        if is_v6 && self.pczt_version != PCZT_VERSION_2 {
            return Err(ParserError::from_str(
                "PCZT version 2 required for V6 transaction",
            ));
        }

        Ok(())
    }

    pub(super) fn read_optional_u32(
        &mut self,
        reader: &mut ByteReader<'_>,
    ) -> Result<Option<u32>, ParserError> {
        match ok!(reader.read_u8()) {
            0 => Ok(None),
            1 => Ok(Some(ok!(reader.read_u32_le()))),
            _ => Err(ParserError::from_str("Bad PCZT Option<u32> tag")),
        }
    }

    pub(super) fn review_outputs(
        &mut self,
        ctx: &mut PcztParserCtx<'_>,
    ) -> Result<(), ParserError> {
        if ctx.tx_info.outputs.is_empty() {
            return Err(ParserError::from_str(
                "No PCZT outputs to display (no transparent outputs, and no Orchard outputs could be decrypted)",
            ));
        }

        let ironwood_vb: i64 = self.ironwood_value_balance;
        let fees_i128 = i128::from(ctx.tx_info.total_amount)
            + i128::from(self.orchard_value_balance)
            + i128::from(ironwood_vb)
            - i128::from(self.total_output_amount);

        if fees_i128 < 0 {
            return Err(ParserError::from_str("Failed to calculate PCZT fees"));
        }

        let fees = u64::try_from(fees_i128)
            .map_err(|_| ParserError::from_str("PCZT fee value out of range"))?;

        debug!(
            "PCZT fees: {}, transparent_input_total={}, transparent_output_total={}, orchard_value_balance={}, ironwood_value_balance={}",
            fees,
            ctx.tx_info.total_amount,
            self.total_output_amount,
            self.orchard_value_balance,
            ironwood_vb
        );

        // In the case of internal transfers between pools (for example, transparent -> Orchard or Orchard -> transparent),
        // we have to display the internal outputs on the clear-sign screen.
        // Not in swap mode: there is no screen to reveal anything on, and clearing `is_change`
        // would make `check_swap_params` see several external outputs where the transaction has one.
        let has_external_output = ctx.tx_info.outputs.iter().any(|output| !output.is_change);
        let reveal_self_outputs = !has_external_output && ctx.swap_params.is_none();
        if reveal_self_outputs {
            debug!("PCZT has no external outputs; displaying self-transfer output");
            // PCZT does not read tx_info.outputs after review; this only affects UI filtering.
            for output in ctx.tx_info.outputs.iter_mut() {
                output.is_change = false;
            }
        }

        let spent_from_public = self.transparent_input_count > 0;
        let spent_from_private = self.orchard_spend_value_sum > 0;
        // Ironwood is a shielded pool; any Ironwood spend must set the from_private flag.
        let spent_from_private = spent_from_private || self.ironwood_spend_value_sum > 0;
        let transfer_type =
            TransferType::classify(spent_from_public, spent_from_private, &ctx.tx_info.outputs);
        // No validation remains after this point. Dropping the decipher cache
        // wipes both IVKs and the OVK before the human review wait.
        self.orchard_fvk = None;
        self.orchard_validation_key = None;
        ctx.tx_info.orchard_decipher_keys = None;
        // Swap mode substitutes validation for review, exactly as the legacy path does: the user
        // already approved the operation in the Exchange app, which drives this flow without
        // interaction, so prompting here would both stall it and ask about something the user has
        // already seen. The cross-check is what makes that safe — it refuses any transaction that
        // does not match what Exchange asked for.
        if let Some(swap_params) = ctx.swap_params {
            ok!(crate::swap::check_swap_params(
                swap_params,
                &ctx.tx_info.outputs,
                fees
            ));
        } else if !ok!(ui_display_tx(
            ctx.comm,
            &ctx.tx_info.outputs,
            fees,
            transfer_type,
            ctx.tx_info.locktime,
            ctx.tx_info.expiry_height,
        )) {
            return Err(ParserError::user());
        }

        self.outputs_reviewed = true;

        Ok(())
    }
}
